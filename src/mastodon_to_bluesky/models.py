from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class MastodonPost(BaseModel):
    id: str
    content: str
    created_at: datetime
    url: str
    in_reply_to_id: Optional[str] = None
    reblog: Optional[dict] = None
    media_attachments: list[dict] = Field(default_factory=list)
    mentions: list[dict] = Field(default_factory=list)
    tags: list[dict] = Field(default_factory=list)
    visibility: str = "public"
    sensitive: bool = False
    spoiler_text: str = ""


class BlueskyPost(BaseModel):
    text: str
    created_at: datetime
    facets: list[dict] = Field(default_factory=list)
    embed: Optional[dict] = None
    reply: Optional[dict] = None


class TransferState(BaseModel):
    last_mastodon_id: Optional[str] = None
    transferred_ids: set[str] = Field(default_factory=set)
    last_updated: datetime = Field(default_factory=datetime.now)