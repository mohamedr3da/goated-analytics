from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from bot.providers.base import XAuthError, XNotFoundError, XProviderError, XRateLimitError
from bot.providers.types import XAccount, XPost, XPostMetrics
from bot.utils.time import parse_x_datetime
from bot.utils.usernames import normalize_x_username


class XApiProvider:
    BASE_URL = "https://api.x.com/2"

    def __init__(
        self,
        bearer_token: str,
        *,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=httpx.Timeout(timeout_seconds),
            headers={"Authorization": f"Bearer {bearer_token}"},
        )

    async def get_account_by_username(self, username: str) -> XAccount:
        normalized = normalize_x_username(username)
        payload = await self._request(
            "GET",
            f"/users/by/username/{normalized}",
            params={
                "user.fields": ",".join(
                    [
                        "id",
                        "username",
                        "name",
                        "protected",
                        "verified",
                        "public_metrics",
                    ]
                )
            },
        )
        data = payload.get("data")
        if not isinstance(data, dict):
            raise XNotFoundError(f"X account @{normalized} was not found.")
        return self._parse_account(data)

    async def get_recent_posts(
        self,
        x_user_id: str,
        *,
        max_results: int,
        since_id: str | None = None,
    ) -> list[XPost]:
        params: dict[str, Any] = {
            "max_results": max(5, min(max_results, 100)),
            "exclude": "retweets",
            "tweet.fields": ",".join(
                [
                    "id",
                    "text",
                    "author_id",
                    "created_at",
                    "public_metrics",
                    "attachments",
                ]
            ),
            "expansions": "attachments.media_keys",
            "media.fields": "public_metrics,type",
        }
        if since_id is not None:
            params["since_id"] = since_id
        payload = await self._request("GET", f"/users/{x_user_id}/tweets", params=params)
        media_by_key = {
            media["media_key"]: media
            for media in payload.get("includes", {}).get("media", [])
            if isinstance(media, dict) and "media_key" in media
        }
        posts = []
        for item in payload.get("data", []) or []:
            if isinstance(item, dict):
                posts.append(self._parse_post(item, media_by_key))
        return posts

    async def health_check(self) -> bool:
        try:
            await self._request(
                "GET",
                "/users/by/username/X",
                params={"user.fields": "id"},
            )
        except XProviderError:
            return False
        return True

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = await self._client.request(method, path, params=params)
            except httpx.TimeoutException as exc:
                last_error = exc
                if attempt == 2:
                    raise XProviderError("X API request timed out.") from exc
                await asyncio.sleep(2**attempt)
                continue
            except httpx.HTTPError as exc:
                raise XProviderError("X API request failed before receiving a response.") from exc

            if response.status_code == 429:
                retry_after = self._retry_after_seconds(response)
                raise XRateLimitError(
                    "X API rate limit reached.",
                    retry_after_seconds=retry_after,
                )
            if response.status_code in {401, 403}:
                raise XAuthError("X API authentication or authorization failed.")
            if response.status_code == 404:
                raise XNotFoundError("X API resource was not found.")
            if response.status_code >= 500:
                last_error = XProviderError(f"X API server error: HTTP {response.status_code}.")
                if attempt == 2:
                    raise last_error
                await asyncio.sleep(2**attempt)
                continue
            if response.status_code >= 400:
                raise XProviderError(f"X API request failed: HTTP {response.status_code}.")
            try:
                return response.json()
            except ValueError as exc:
                raise XProviderError("X API returned invalid JSON.") from exc
        raise XProviderError("X API request failed.") from last_error

    def _retry_after_seconds(self, response: httpx.Response) -> int | None:
        retry_after = response.headers.get("retry-after")
        if retry_after and retry_after.isdigit():
            return int(retry_after)
        reset = response.headers.get("x-rate-limit-reset")
        if reset and reset.isdigit():
            return max(0, int(reset) - int(datetime.now(UTC).timestamp()))
        if retry_after:
            try:
                retry_at = parsedate_to_datetime(retry_after)
            except (TypeError, ValueError):
                return None
            return max(0, int((retry_at.astimezone(UTC) - datetime.now(UTC)).total_seconds()))
        return None

    def _parse_account(self, data: dict[str, Any]) -> XAccount:
        metrics = data.get("public_metrics") or {}
        return XAccount(
            id=str(data["id"]),
            username=str(data["username"]),
            display_name=str(data.get("name") or data["username"]),
            protected=bool(data.get("protected", False)),
            verified=bool(data.get("verified", False)),
            followers_count=metrics.get("followers_count"),
            following_count=metrics.get("following_count"),
            post_count=metrics.get("post_count") or metrics.get("tweet_count"),
            listed_count=metrics.get("listed_count"),
            raw=data,
        )

    def _parse_post(self, data: dict[str, Any], media_by_key: dict[str, dict[str, Any]]) -> XPost:
        public_metrics = data.get("public_metrics") or {}
        video_view_count = None
        for media_key in data.get("attachments", {}).get("media_keys", []) or []:
            media_metrics = (media_by_key.get(media_key) or {}).get("public_metrics") or {}
            media_view_count = media_metrics.get("view_count")
            if media_view_count is not None:
                video_view_count = (video_view_count or 0) + media_view_count

        post_id = str(data["id"])
        author_id = str(data.get("author_id") or "")
        return XPost(
            id=post_id,
            author_id=author_id,
            created_at=parse_x_datetime(str(data["created_at"])),
            text=str(data.get("text") or ""),
            url=f"https://x.com/i/status/{post_id}",
            metrics=XPostMetrics(
                impression_count=public_metrics.get("impression_count"),
                like_count=public_metrics.get("like_count"),
                reply_count=public_metrics.get("reply_count"),
                repost_count=public_metrics.get("retweet_count")
                if public_metrics.get("retweet_count") is not None
                else public_metrics.get("repost_count"),
                quote_count=public_metrics.get("quote_count"),
                bookmark_count=public_metrics.get("bookmark_count"),
                video_view_count=video_view_count,
                raw=public_metrics,
            ),
            raw=data,
        )
