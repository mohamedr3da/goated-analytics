from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from bot.providers.base import XProviderError
from bot.providers.scraper.errors import NavigationTimeout, RateLimited
from bot.providers.scraper.models import ScrapeResult
from bot.providers.scraper.parser import parse_public_profile_page
from bot.providers.types import XAccount, XPost, XRateLimitState
from bot.utils.usernames import normalize_x_username


class PublicScraperProvider:
    """Experimental unauthenticated provider for public X profile pages."""

    BASE_URL = "https://x.com"

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 20.0,
        recent_post_limit: int = 10,
    ) -> None:
        self._owns_client = client is None
        self._recent_post_limit = recent_post_limit
        self._usernames_by_id: dict[str, str] = {}
        self._scrapes_by_username: dict[str, ScrapeResult] = {}
        self._scrape_limits_by_username: dict[str, int] = {}
        self.last_rate_limit: XRateLimitState | None = None
        self.last_scrape_stats: dict[str, Any] | None = None
        self._client = client or httpx.AsyncClient(
            base_url=self.BASE_URL,
            follow_redirects=True,
            timeout=httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 10.0)),
            headers={
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "user-agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/140.0.0.0 Safari/537.36"
                ),
            },
        )

    async def get_account_by_username(self, username: str) -> XAccount:
        scrape = await self._scrape_username(username, max_posts=self._recent_post_limit)
        profile = scrape.profile
        self._usernames_by_id[profile.x_user_id] = profile.username
        return XAccount(
            id=profile.x_user_id,
            username=profile.username,
            display_name=profile.display_name,
            protected=profile.protected,
            verified=profile.verified,
            followers_count=profile.followers_count,
            following_count=profile.following_count,
            post_count=profile.post_count,
            listed_count=profile.listed_count,
            profile_image_url=profile.profile_image_url,
            created_at=profile.created_at,
            verified_type=profile.verified_type,
            raw=profile.raw,
        )

    async def get_recent_posts(
        self,
        x_user_id: str,
        *,
        max_results: int,
        since_id: str | None = None,
    ) -> list[XPost]:
        username = self._usernames_by_id.get(x_user_id)
        if username is None:
            raise XProviderError(
                "Public scraper needs a username resolved in this process before fetching posts."
            )
        max_posts = min(max_results, self._recent_post_limit)
        cache_key = normalize_x_username(username).casefold()
        scrape = self._scrapes_by_username.get(cache_key)
        cached_limit = self._scrape_limits_by_username.get(cache_key, -1)
        if scrape is None or cached_limit < max_posts:
            scrape = await self._scrape_username(username, max_posts=max_posts)
        return [
            _to_x_post(post)
            for post in scrape.posts
            if since_id is None or post.id > since_id
        ]

    async def get_posts_window(
        self,
        x_user_id: str,
        *,
        start_time: datetime,
        end_time: datetime,
        max_posts: int,
    ) -> list[XPost]:
        posts = await self.get_recent_posts(
            x_user_id,
            max_results=min(max_posts, self._recent_post_limit),
        )
        return [post for post in posts if start_time <= post.created_at <= end_time][:max_posts]

    async def health_check(self) -> bool:
        try:
            await self.get_account_by_username("rawdogmoon")
        except XProviderError:
            return False
        return True

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _scrape_username(self, username: str, *, max_posts: int):
        normalized = normalize_x_username(username)
        try:
            response = await self._client.get(f"/{normalized}")
        except httpx.TimeoutException as exc:
            raise NavigationTimeout("Public X page request timed out.") from exc
        except httpx.HTTPError as exc:
            raise XProviderError("Public X page request failed.") from exc
        finally:
            self._client.cookies.clear()
        if response.status_code == 429:
            raise RateLimited("Public X page access was rate limited.")
        if response.status_code >= 400:
            raise XProviderError(f"Public X page returned HTTP {response.status_code}.")
        scrape = parse_public_profile_page(
            response.text,
            requested_username=normalized,
            max_posts=max_posts,
        )
        normalized_key = normalized.casefold()
        profile_key = scrape.profile.username.casefold()
        self._scrapes_by_username[normalized_key] = scrape
        self._scrapes_by_username[profile_key] = scrape
        self._scrape_limits_by_username[normalized_key] = max_posts
        self._scrape_limits_by_username[profile_key] = max_posts
        if scrape.profile.x_user_id:
            self._usernames_by_id[scrape.profile.x_user_id] = scrape.profile.username
        self.last_scrape_stats = {
            "pages_loaded": scrape.stats.pages_loaded,
            "posts_extracted": scrape.stats.posts_extracted,
            "metrics_extracted": scrape.stats.metrics_extracted,
            "missing_metrics": scrape.stats.missing_metrics,
            "parse_failures": scrape.stats.parse_failures,
            "login_wall": scrape.stats.login_wall,
            "blocked": scrape.stats.blocked,
        }
        return scrape


def _to_x_post(post) -> XPost:
    return XPost(
        id=post.id,
        author_id=post.author_id,
        created_at=post.created_at,
        text=post.text,
        url=post.url,
        metrics=post.metrics,
        post_type=post.post_type,
        referenced_post_id=post.referenced_post_id,
        conversation_id=post.conversation_id,
        lang=post.lang,
        possibly_sensitive=post.possibly_sensitive,
        raw=post.raw,
    )
