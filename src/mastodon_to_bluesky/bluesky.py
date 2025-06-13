import re
import time
from datetime import datetime
from typing import Optional

import httpx
from rich.console import Console

from mastodon_to_bluesky.models import BlueskyPost

console = Console()


class BlueskyClient:
    def __init__(self, handle: str, password: str):
        self.handle = handle
        self.password = password
        self.pds_url = "https://bsky.social"
        self.client = httpx.Client(timeout=30.0)
        self.session = None
        self.did = None
    
    def authenticate(self):
        """Authenticate with Bluesky using app password."""
        response = self.client.post(
            f"{self.pds_url}/xrpc/com.atproto.server.createSession",
            json={
                "identifier": self.handle,
                "password": self.password,
            },
        )
        response.raise_for_status()
        
        self.session = response.json()
        self.did = self.session["did"]
        
        # Set auth header for future requests
        self.client.headers["Authorization"] = f"Bearer {self.session['accessJwt']}"
        
        console.print(f"[green]✓[/green] Authenticated as {self.handle}")
    
    def create_post(self, post: BlueskyPost) -> dict:
        """Create a post on Bluesky."""
        record = {
            "$type": "app.bsky.feed.post",
            "text": post.text,
            "createdAt": post.created_at.isoformat() + "Z",
        }
        
        # Add facets (mentions, links, hashtags)
        if post.facets:
            record["facets"] = post.facets
        
        # Add embed (images, quote posts, etc.)
        if post.embed:
            record["embed"] = post.embed
        
        # Add reply reference
        if post.reply:
            record["reply"] = post.reply
        
        response = self.client.post(
            f"{self.pds_url}/xrpc/com.atproto.repo.createRecord",
            json={
                "repo": self.did,
                "collection": "app.bsky.feed.post",
                "record": record,
            },
        )
        response.raise_for_status()
        
        return response.json()
    
    def upload_image(self, image_data: bytes, mime_type: str = "image/jpeg") -> dict:
        """Upload an image to Bluesky."""
        response = self.client.post(
            f"{self.pds_url}/xrpc/com.atproto.repo.uploadBlob",
            headers={"Content-Type": mime_type},
            content=image_data,
        )
        response.raise_for_status()
        
        return response.json()["blob"]
    
    def resolve_handle(self, handle: str) -> Optional[str]:
        """Resolve a handle to a DID."""
        try:
            response = self.client.get(
                f"{self.pds_url}/xrpc/com.atproto.identity.resolveHandle",
                params={"handle": handle},
            )
            response.raise_for_status()
            return response.json()["did"]
        except httpx.HTTPStatusError:
            return None
    
    def parse_mentions(self, text: str) -> tuple[str, list[dict]]:
        """Parse mentions in text and create facets."""
        facets = []
        mention_pattern = re.compile(r'@([a-zA-Z0-9.-]+)')
        
        for match in mention_pattern.finditer(text):
            handle = match.group(1)
            
            # Skip if not a valid handle format
            if "." not in handle:
                continue
            
            # Try to resolve the handle
            did = self.resolve_handle(handle)
            if did:
                facets.append({
                    "index": {
                        "byteStart": match.start(),
                        "byteEnd": match.end(),
                    },
                    "features": [{
                        "$type": "app.bsky.richtext.facet#mention",
                        "did": did,
                    }],
                })
        
        return text, facets
    
    def parse_links(self, text: str, existing_facets: list[dict]) -> list[dict]:
        """Parse URLs in text and add link facets."""
        url_pattern = re.compile(
            r'https?://(?:www\.)?[-a-zA-Z0-9@:%._+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b'
            r'(?:[-a-zA-Z0-9()@:%_+.~#?&/=]*)'
        )
        
        facets = existing_facets.copy()
        
        for match in url_pattern.finditer(text):
            # Check if this range overlaps with existing facets
            overlaps = any(
                facet["index"]["byteStart"] <= match.start() < facet["index"]["byteEnd"] or
                facet["index"]["byteStart"] < match.end() <= facet["index"]["byteEnd"]
                for facet in facets
            )
            
            if not overlaps:
                facets.append({
                    "index": {
                        "byteStart": match.start(),
                        "byteEnd": match.end(),
                    },
                    "features": [{
                        "$type": "app.bsky.richtext.facet#link",
                        "uri": match.group(0),
                    }],
                })
        
        return facets
    
    def parse_hashtags(self, text: str, existing_facets: list[dict]) -> list[dict]:
        """Parse hashtags in text and add tag facets."""
        hashtag_pattern = re.compile(r'#(\w+)')
        
        facets = existing_facets.copy()
        
        for match in hashtag_pattern.finditer(text):
            # Check if this range overlaps with existing facets
            overlaps = any(
                facet["index"]["byteStart"] <= match.start() < facet["index"]["byteEnd"] or
                facet["index"]["byteStart"] < match.end() <= facet["index"]["byteEnd"]
                for facet in facets
            )
            
            if not overlaps:
                facets.append({
                    "index": {
                        "byteStart": match.start(),
                        "byteEnd": match.end(),
                    },
                    "features": [{
                        "$type": "app.bsky.richtext.facet#tag",
                        "tag": match.group(1),
                    }],
                })
        
        return facets
    
    def create_rich_text(self, text: str) -> tuple[str, list[dict]]:
        """Create rich text with facets for mentions, links, and hashtags."""
        # Parse mentions first (they might contain dots that look like URLs)
        text, facets = self.parse_mentions(text)
        
        # Parse links
        facets = self.parse_links(text, facets)
        
        # Parse hashtags
        facets = self.parse_hashtags(text, facets)
        
        return text, facets
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.client.close()