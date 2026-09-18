from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class XRateLimitState:
    limit: int | None
    remaining: int | None
    reset_epoch: int | None


@dataclass(frozen=True)
class XAccount:
    id: str
    username: str
    display_name: str
    protected: bool
    verified: bool
    followers_count: int | None
    following_count: int | None
    post_count: int | None
    listed_count: int | None
    profile_image_url: str | None = None
    created_at: datetime | None = None
    verified_type: str | None = None
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class XPostMetrics:
    impression_count: int | None
    like_count: int | None
    reply_count: int | None
    repost_count: int | None
    quote_count: int | None
    bookmark_count: int | None
    video_view_count: int | None
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class XPost:
    id: str
    author_id: str
    created_at: datetime
    text: str
    url: str
    metrics: XPostMetrics
    post_type: str = "post"
    referenced_post_id: str | None = None
    conversation_id: str | None = None
    lang: str | None = None
    possibly_sensitive: bool | None = None
    raw: dict = field(default_factory=dict)
