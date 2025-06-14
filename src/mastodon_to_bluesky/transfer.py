import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from bs4 import BeautifulSoup
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeRemainingColumn

from mastodon_to_bluesky.bluesky import BlueskyClient
from mastodon_to_bluesky.mastodon import MastodonClient
from mastodon_to_bluesky.models import BlueskyPost, MastodonPost, RetryInfo, TransferState

console = Console()


class TransferManager:
    def __init__(
        self,
        mastodon_client: MastodonClient,
        bluesky_client: BlueskyClient,
        state_file: Path,
        dry_run: bool = False,
        max_retries: int = 3,
        retry_delay: int = 60,
    ):
        self.mastodon = mastodon_client
        self.bluesky = bluesky_client
        self.state_file = state_file
        self.dry_run = dry_run
        self.max_retries = max_retries
        self.retry_delay = retry_delay  # Base delay in seconds
        self.state = self._load_state()

    def _load_state(self) -> TransferState:
        """Load transfer state from file."""
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    data = json.load(f)
                    return TransferState(**data)
            except Exception as e:
                console.print(f"[yellow]Warning: Could not load state file: {e}[/yellow]")

        return TransferState()

    def _save_state(self):
        """Save transfer state to file."""
        if not self.dry_run:
            with open(self.state_file, "w") as f:
                json.dump(self.state.model_dump(mode="json"), f, indent=2, default=str)

    def transfer_posts(
        self,
        limit: int | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        skip_existing: bool = True,
        include_replies: bool = False,
        include_boosts: bool = False,
    ) -> dict:
        """Transfer posts from Mastodon to Bluesky."""
        console.print("[bold]Fetching posts from Mastodon...[/bold]")

        # Fetch posts and convert to list
        posts_iterator = self.mastodon.get_posts(
            limit=limit,
            since=since,
            until=until,
            include_replies=include_replies,
            include_boosts=include_boosts,
        )
        
        # Convert iterator to list to get count and allow reversal
        posts = list(posts_iterator)

        if not posts:
            console.print("[yellow]No posts found matching criteria[/yellow]")
            return {"processed": 0, "transferred": 0, "skipped": 0, "errors": 0}

        console.print(f"Found {len(posts)} posts to process")

        # Process posts in reverse chronological order (oldest first)
        posts.reverse()

        # Statistics
        stats = {"processed": 0, "transferred": 0, "skipped": 0, "errors": 0}

        # Process posts with progress bar
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            "[progress.percentage]{task.percentage:>3.0f}%",
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Transferring posts...", total=len(posts))

            for post in posts:
                try:
                    stats["processed"] += 1

                    # Skip if already transferred
                    if skip_existing and post.id in self.state.transferred_ids:
                        stats["skipped"] += 1
                        progress.update(task, advance=1)
                        continue

                    # Convert and create post
                    if self.dry_run:
                        console.print(f"[dim]Would transfer post {post.id}: {post.content[:50]}...[/dim]")
                        stats["transferred"] += 1
                    else:
                        success = self._transfer_post(post)
                        if success:
                            self.state.transferred_ids.add(post.id)
                            self.state.last_mastodon_id = post.id
                            self.state.last_updated = datetime.now()
                            self._save_state()
                            stats["transferred"] += 1
                        else:
                            stats["errors"] += 1

                except Exception as e:
                    console.print(f"[red]Error transferring post {post.id}: {e}[/red]")
                    stats["errors"] += 1

                progress.update(task, advance=1)

        return stats

    def _transfer_post(self, mastodon_post: MastodonPost) -> bool:
        """Transfer a single post to Bluesky. Returns True if successful."""
        try:
            # Convert HTML content to plain text
            text = self._html_to_text(mastodon_post.content)

            # Handle content warnings
            if mastodon_post.spoiler_text:
                text = f"CW: {mastodon_post.spoiler_text}\n\n{text}"
            
            # Add original date to preserve timestamp information
            original_date = mastodon_post.created_at.strftime("%Y-%m-%d %H:%M UTC")
            text = f"{text}\n\n[Originally posted: {original_date}]"
            
            # Add notes about unsupported media types
            if mastodon_post.media_attachments:
                unsupported_types = set()
                for attachment in mastodon_post.media_attachments:
                    if attachment["type"] != "image":
                        unsupported_types.add(attachment["type"])
                
                if unsupported_types:
                    for media_type in unsupported_types:
                        text += f"\n\n[Media type '{media_type}' not supported]"

            # Split long posts if necessary
            posts_to_create = self._split_text(text, 300)

            # Handle media attachments
            embed = None
            if mastodon_post.media_attachments and not self.dry_run:
                embed = self._create_media_embed(mastodon_post.media_attachments[:4])  # Max 4 images

            # Create posts (as thread if multiple)
            parent_ref = None
            for i, post_text in enumerate(posts_to_create):
                # Create rich text with facets
                post_text, facets = self.bluesky.create_rich_text(post_text)

                # Create post
                # Use current time as Bluesky doesn't support backdating
                from datetime import datetime
                bluesky_post = BlueskyPost(
                    text=post_text,
                    created_at=datetime.now(),
                    facets=facets,
                    embed=embed if i == 0 else None,  # Only add images to first post
                    reply=parent_ref,
                )

                if self.dry_run:
                    console.print(f"[dim]Would create post: {post_text[:50]}...[/dim]")
                    result = {"uri": "dry-run-uri", "cid": "dry-run-cid"}
                else:
                    result = self.bluesky.create_post(bluesky_post)

                # Set up parent reference for thread
                if i == 0 and len(posts_to_create) > 1:
                    parent_ref = {
                        "root": {
                            "uri": result["uri"],
                            "cid": result["cid"],
                        },
                        "parent": {
                            "uri": result["uri"],
                            "cid": result["cid"],
                        },
                    }
                elif parent_ref:
                    parent_ref["parent"] = {
                        "uri": result["uri"],
                        "cid": result["cid"],
                    }

            return True

        except Exception as e:
            console.print(f"[red]Error transferring post {mastodon_post.id}: {str(e)}[/red]")
            self._add_to_retry_queue(mastodon_post, e)
            return False

    def _html_to_text(self, html: str) -> str:
        """Convert HTML content to plain text."""
        # Parse HTML
        soup = BeautifulSoup(html, "html.parser")

        # Replace <br> with newlines
        for br in soup.find_all("br"):
            br.replace_with("\n")

        # Replace <p> with double newlines
        for p in soup.find_all("p"):
            p.insert_after("\n\n")

        # Get text
        text = soup.get_text()

        # Clean up extra whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.strip()

        return text

    def _split_text(self, text: str, max_length: int) -> list[str]:
        """Split text into chunks that fit within max_length."""
        if len(text) <= max_length:
            return [text]

        # Split by sentences first
        sentences = re.split(r"(?<=[.!?])\s+", text)

        chunks = []
        current_chunk = ""

        for sentence in sentences:
            # If a single sentence is too long, split by words
            if len(sentence) > max_length:
                words = sentence.split()
                for word in words:
                    if len(current_chunk) + len(word) + 1 <= max_length - 10:  # Leave room for "..."
                        current_chunk += (" " if current_chunk else "") + word
                    else:
                        if current_chunk:
                            chunks.append(current_chunk + "...")
                        current_chunk = "..." + word
            elif len(current_chunk) + len(sentence) + 1 <= max_length - 10:
                current_chunk += (" " if current_chunk else "") + sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk + "...")
                current_chunk = "..." + sentence

        if current_chunk:
            chunks.append(current_chunk)

        # Add thread indicators
        if len(chunks) > 1:
            for i, chunk in enumerate(chunks):
                chunks[i] = f"[{i + 1}/{len(chunks)}] {chunk}"

        return chunks

    def _create_media_embed(self, attachments: list[dict]) -> dict:
        """Create media embed for Bluesky post."""
        images = []

        for attachment in attachments:
            if attachment["type"] == "image":
                # Download image
                image_data = self.mastodon.download_media(attachment["url"])

                # Upload to Bluesky
                blob = self.bluesky.upload_image(image_data)

                # Add to images list
                image = {"image": blob}
                if attachment.get("description"):
                    image["alt"] = attachment["description"][:1000]  # Bluesky alt text limit

                images.append(image)

        if images:
            return {
                "$type": "app.bsky.embed.images",
                "images": images,
            }

    def _categorize_error(self, error: Exception) -> str:
        """Categorize error type for retry logic."""
        error_str = str(error).lower()

        if "rate limit" in error_str or "429" in error_str:
            return "rate_limit"
        elif "network" in error_str or "connection" in error_str or "timeout" in error_str:
            return "network"
        elif "api" in error_str or "400" in error_str or "401" in error_str:
            return "api_error"
        else:
            return "unknown"

    def _calculate_retry_delay(self, attempt: int, error_type: str) -> int:
        """Calculate delay before next retry using exponential backoff."""
        if error_type == "rate_limit":
            # Longer delay for rate limits
            base_delay = self.retry_delay * 2
        else:
            base_delay = self.retry_delay

        # Exponential backoff: delay * 2^(attempt-1)
        delay = base_delay * (2 ** (attempt - 1))

        # Cap at 30 minutes
        return min(delay, 1800)

    def _add_to_retry_queue(self, post: MastodonPost, error: Exception):
        """Add failed post to retry queue."""
        error_type = self._categorize_error(error)
        post_id = post.id

        if post_id in self.state.retry_queue:
            # Update existing retry info
            retry_info = self.state.retry_queue[post_id]
            retry_info.attempt_count += 1
            retry_info.last_attempt = datetime.now()
            retry_info.error_message = str(error)
            retry_info.error_type = error_type

            if retry_info.attempt_count < self.max_retries:
                delay = self._calculate_retry_delay(retry_info.attempt_count, error_type)
                retry_info.next_retry = datetime.now() + timedelta(seconds=delay)
            else:
                # Max retries reached, move to failed
                self.state.failed_ids.add(post_id)
                del self.state.retry_queue[post_id]
        else:
            # New retry entry with post data
            retry_info = RetryInfo(
                post_id=post_id,
                post_data=post.model_dump(mode="json"),  # Serialize post data
                error_type=error_type,
                error_message=str(error),
                attempt_count=1,
            )

            if retry_info.attempt_count < self.max_retries:
                delay = self._calculate_retry_delay(1, error_type)
                retry_info.next_retry = datetime.now() + timedelta(seconds=delay)
                self.state.retry_queue[post_id] = retry_info
            else:
                self.state.failed_ids.add(post_id)

    def process_retry_queue(self) -> dict:
        """Process posts in the retry queue."""
        stats = {"retried": 0, "succeeded": 0, "failed": 0}

        if not self.state.retry_queue:
            return stats

        console.print(f"[yellow]Processing {len(self.state.retry_queue)} posts in retry queue...[/yellow]")

        # Get posts ready for retry
        ready_for_retry = []
        now = datetime.now()

        for post_id, retry_info in self.state.retry_queue.items():
            if retry_info.next_retry and retry_info.next_retry <= now:
                ready_for_retry.append((post_id, retry_info))

        if not ready_for_retry:
            console.print("[yellow]No posts ready for retry yet.[/yellow]")
            return stats

        # Process posts from retry queue
        for post_id, retry_info in ready_for_retry:
            console.print(
                f"[yellow]Retrying post {post_id} (attempt {retry_info.attempt_count + 1}/{self.max_retries})...[/yellow]"
            )

            stats["retried"] += 1

            try:
                # Reconstruct the MastodonPost from stored data
                post = MastodonPost(**retry_info.post_data)
                
                # Actually retry the transfer
                success = self._transfer_post(post)
                
                if success:
                    # Remove from retry queue and mark as transferred
                    del self.state.retry_queue[post_id]
                    self.state.transferred_ids.add(post_id)
                    self.state.last_mastodon_id = post_id
                    self.state.last_updated = datetime.now()
                    self._save_state()
                    stats["succeeded"] += 1
                    console.print(f"[green]✓ Successfully retried post {post_id}[/green]")
                else:
                    # Transfer failed again - retry info will be updated by _add_to_retry_queue
                    stats["failed"] += 1
                    
            except Exception as e:
                console.print(f"[red]Error retrying post {post_id}: {str(e)}[/red]")
                stats["failed"] += 1
                # Remove corrupted entries
                if post_id in self.state.retry_queue:
                    del self.state.retry_queue[post_id]
                self.state.failed_ids.add(post_id)

        self._save_state()
        return stats
