from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from bot.providers.types import XAccount, XPost, XPostMetrics
from bot.utils.usernames import normalize_x_username


class MockXAnalyticsProvider:
    """Deterministic development provider used when real X credentials are not configured."""

    async def get_account_by_username(self, username: str) -> XAccount:
        normalized = normalize_x_username(username)
        seed = int(hashlib.sha256(normalized.lower().encode()).hexdigest()[:8], 16)
        tick = int(datetime.now(UTC).timestamp() // 3600)
        followers = 1_000 + (seed % 50_000) + (tick % 500)
        return XAccount(
            id=str(10_000_000_000 + seed),
            username=normalized,
            display_name=f"{normalized} (mock)",
            protected=False,
            verified=False,
            followers_count=followers,
            following_count=seed % 2_000,
            post_count=100 + (seed % 5_000),
            listed_count=seed % 100,
            raw={"provider": "mock"},
        )

    async def get_recent_posts(
        self,
        x_user_id: str,
        *,
        max_results: int,
        since_id: str | None = None,
    ) -> list[XPost]:
        now = datetime.now(UTC).replace(microsecond=0)
        limit = max(1, min(max_results, 10))
        posts: list[XPost] = []
        seed = int(hashlib.sha256(x_user_id.encode()).hexdigest()[:8], 16)
        tick = int(now.timestamp() // 1800)
        for index in range(limit):
            post_id = str(seed * 100 + index)
            if since_id is not None and post_id <= since_id:
                continue
            created_at = now - timedelta(hours=index * 6)
            impressions = 500 + (seed % 3_000) + (tick * (index + 1)) % 1_000
            posts.append(
                XPost(
                    id=post_id,
                    author_id=x_user_id,
                    created_at=created_at,
                    text=f"Mock post {index + 1}",
                    url=f"https://x.com/i/status/{post_id}",
                    metrics=XPostMetrics(
                        impression_count=impressions,
                        like_count=impressions // 12,
                        reply_count=impressions // 120,
                        repost_count=impressions // 80,
                        quote_count=impressions // 250,
                        bookmark_count=impressions // 100,
                        video_view_count=None,
                        raw={"provider": "mock"},
                    ),
                    raw={"provider": "mock"},
                )
            )
        return posts

    async def health_check(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None

