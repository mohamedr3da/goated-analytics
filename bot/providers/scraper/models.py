from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from bot.providers.types import XPostMetrics


@dataclass(frozen=True)
class ScrapedProfile:
    x_user_id: str
    username: str
    display_name: str
    protected: bool
    verified: bool
    followers_count: int | None
    following_count: int | None
    post_count: int | None
    listed_count: int | None
    profile_image_url: str | None
    created_at: datetime | None
    verified_type: str | None
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ScrapedPost:
    id: str
    author_id: str
    created_at: datetime
    text: str
    url: str
    metrics: XPostMetrics
    post_type: str
    referenced_post_id: str | None = None
    conversation_id: str | None = None
    lang: str | None = None
    possibly_sensitive: bool | None = None
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ScrapeStats:
    pages_loaded: int = 1
    posts_extracted: int = 0
    metrics_extracted: int = 0
    missing_metrics: int = 0
    parse_failures: int = 0
    login_wall: bool = False
    blocked: bool = False


@dataclass(frozen=True)
class ScrapeResult:
    profile: ScrapedProfile
    posts: list[ScrapedPost]
    stats: ScrapeStats
