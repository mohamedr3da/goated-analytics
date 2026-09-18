from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


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
    raw: dict = field(default_factory=dict)

