import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeRemainingColumn

from mastodon_to_bluesky.bluesky import BlueskyClient
from mastodon_to_bluesky.mastodon import MastodonClient
from mastodon_to_bluesky.models import BlueskyPost, MastodonPost, TransferState

console = Console()


class TransferManager:
    def __init__(
        self,
        mastodon_client: MastodonClient,
        bluesky_client: BlueskyClient,
        state_file: Path,
        dry_run: bool = False,
    ):
        self.mastodon = mastodon_client
        self.bluesky = bluesky_client
        self.state_file = state_file
        self.dry_run = dry_run
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
        limit: Optional[int] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        skip_existing: bool = True,
        include_replies: bool = False,
        include_boosts: bool = False,
    ) -> dict:
        """Transfer posts from Mastodon to Bluesky."""
        console.print("[bold]Fetching posts from Mastodon...[/bold]")
        
        # Fetch posts
        posts = self.mastodon.get_posts(
            limit=limit,
            since=since,
            until=until,
            include_replies=include_replies,
            include_boosts=include_boosts,
        )
        
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
                    else:
                        self._transfer_post(post)
                        self.state.transferred_ids.add(post.id)
                        self.state.last_mastodon_id = post.id
                        self.state.last_updated = datetime.now()
                        self._save_state()
                    
                    stats["transferred"] += 1
                    
                except Exception as e:
                    console.print(f"[red]Error transferring post {post.id}: {e}[/red]")
                    stats["errors"] += 1
                
                progress.update(task, advance=1)
        
        return stats
    
    def _transfer_post(self, mastodon_post: MastodonPost):
        """Transfer a single post to Bluesky."""
        # Convert HTML content to plain text
        text = self._html_to_text(mastodon_post.content)
        
        # Handle content warnings
        if mastodon_post.spoiler_text:
            text = f"CW: {mastodon_post.spoiler_text}\n\n{text}"
        
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
            bluesky_post = BlueskyPost(
                text=post_text,
                created_at=mastodon_post.created_at,
                facets=facets,
                embed=embed if i == 0 else None,  # Only add images to first post
                reply=parent_ref,
            )
            
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
                chunks[i] = f"[{i+1}/{len(chunks)}] {chunk}"
        
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
        
        return None