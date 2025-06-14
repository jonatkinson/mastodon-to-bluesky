import time
from datetime import datetime
from urllib.parse import urlparse

import httpx
from rich.console import Console

from mastodon_to_bluesky.models import MastodonPost

console = Console()


class MastodonClient:
    def __init__(self, instance_url: str, access_token: str):
        self.instance_url = instance_url.rstrip("/")
        self.access_token = access_token
        self.client = httpx.Client(
            base_url=f"{self.instance_url}/api/v1",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30.0,
        )
        self.account_id = None
        self.rate_limit_remaining = None
        self.rate_limit_reset = None

    def authenticate(self):
        """Verify credentials and get account info."""
        response = self.client.get("/accounts/verify_credentials")
        response.raise_for_status()
        account = response.json()
        self.account_id = account["id"]
        console.print(f"[green]✓[/green] Authenticated as @{account['username']}")
        return account
    
    def verify_credentials(self) -> bool:
        """Verify credentials. Returns True if successful."""
        try:
            self.authenticate()
            return True
        except Exception:
            return False

    def get_posts(
        self,
        limit: int | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        include_replies: bool = False,
        include_boosts: bool = False,
        max_id: str | None = None,
    ) -> list[MastodonPost]:
        """Fetch posts from the authenticated user's timeline."""
        posts = []
        params = {
            "exclude_replies": not include_replies,
            "exclude_reblogs": not include_boosts,
            "limit": min(limit or 40, 40),  # Mastodon max is 40 per request
        }

        if max_id:
            params["max_id"] = max_id

        while True:
            # Handle rate limiting
            self._handle_rate_limit()

            response = self.client.get(
                f"/accounts/{self.account_id}/statuses",
                params=params,
            )
            response.raise_for_status()

            # Update rate limit info
            self._update_rate_limit(response)

            batch = response.json()
            if not batch:
                break

            for post_data in batch:
                # Handle different datetime formats from Mastodon
                created_at_str = post_data["created_at"]
                if created_at_str.endswith("Z"):
                    created_at_str = created_at_str[:-1] + "+00:00"

                post = MastodonPost(
                    id=post_data["id"],
                    content=post_data["content"],
                    created_at=datetime.fromisoformat(created_at_str),
                    url=post_data["url"],
                    in_reply_to_id=post_data.get("in_reply_to_id"),
                    reblog=post_data.get("reblog"),
                    media_attachments=post_data.get("media_attachments", []),
                    mentions=post_data.get("mentions", []),
                    tags=post_data.get("tags", []),
                    visibility=post_data.get("visibility", "public"),
                    sensitive=post_data.get("sensitive", False),
                    spoiler_text=post_data.get("spoiler_text", ""),
                )

                # Filter by date if specified
                if since and post.created_at < since:
                    return posts  # Posts are in reverse chronological order
                if until and post.created_at > until:
                    continue

                posts.append(post)

                if limit and len(posts) >= limit:
                    return posts

            # Get next page
            link_header = response.headers.get("Link", "")
            next_url = self._parse_link_header(link_header, "next")
            if not next_url:
                break

            # Extract max_id from next URL
            parsed_url = urlparse(next_url)
            params["max_id"] = parsed_url.query.split("max_id=")[1].split("&")[0]

        return posts

    def download_media(self, url: str) -> bytes:
        """Download media attachment."""
        response = httpx.get(url, timeout=60.0)
        response.raise_for_status()
        return response.content

    def _handle_rate_limit(self):
        """Handle rate limiting by waiting if necessary."""
        if self.rate_limit_remaining is not None and self.rate_limit_remaining <= 1:
            if self.rate_limit_reset:
                wait_time = max(0, self.rate_limit_reset - time.time())
                if wait_time > 0:
                    console.print(f"[yellow]Rate limit reached. Waiting {wait_time:.0f} seconds...[/yellow]")
                    time.sleep(wait_time + 1)

    def _update_rate_limit(self, response: httpx.Response):
        """Update rate limit information from response headers."""
        if "X-RateLimit-Remaining" in response.headers:
            try:
                self.rate_limit_remaining = int(response.headers["X-RateLimit-Remaining"])
            except ValueError:
                pass
        if "X-RateLimit-Reset" in response.headers:
            try:
                # Try to parse as timestamp
                reset_value = response.headers["X-RateLimit-Reset"]
                # Handle ISO format datetime
                if "T" in reset_value:
                    reset_dt = datetime.fromisoformat(reset_value.replace("Z", "+00:00"))
                    self.rate_limit_reset = reset_dt.timestamp()
                else:
                    # Handle Unix timestamp
                    self.rate_limit_reset = float(reset_value)
            except (ValueError, AttributeError):
                pass

    def _parse_link_header(self, link_header: str, rel: str) -> str | None:
        """Parse Link header to find URL with specified rel."""
        if not link_header:
            return None

        links = link_header.split(",")
        for link in links:
            parts = link.split(";")
            if len(parts) == 2:
                url = parts[0].strip()[1:-1]  # Remove < and >
                rel_part = parts[1].strip()
                if f'rel="{rel}"' in rel_part:
                    return url

        return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.client.close()
