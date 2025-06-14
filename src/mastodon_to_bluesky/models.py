from datetime import datetime

from pydantic import BaseModel, Field


class MastodonPost(BaseModel):
    id: str
    content: str
    created_at: datetime
    url: str
    in_reply_to_id: str | None = None
    reblog: dict | None = None
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
    embed: dict | None = None
    reply: dict | None = None


class RetryInfo(BaseModel):
    """Information about a retry attempt."""

    post_id: str
    post_data: dict  # Serialized MastodonPost data
    error_type: str  # "rate_limit", "network", "api_error", "unknown"
    error_message: str
    attempt_count: int = 1
    last_attempt: datetime = Field(default_factory=datetime.now)
    next_retry: datetime | None = None


class TransferState(BaseModel):
    last_mastodon_id: str | None = None
    transferred_ids: set[str] = Field(default_factory=set)
    failed_ids: set[str] = Field(default_factory=set)
    retry_queue: dict[str, RetryInfo] = Field(default_factory=dict)
    last_updated: datetime = Field(default_factory=datetime.now)
