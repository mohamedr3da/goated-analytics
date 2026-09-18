from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from inspect import isawaitable
from random import Random
from typing import Any

import httpx

from bot.providers.base import (
    XAuthError,
    XMalformedResponseError,
    XNotFoundError,
    XProviderError,
    XRateLimitError,
)
from bot.providers.types import XAccount, XPost, XPostMetrics, XRateLimitState
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
        max_retries: int = 3,
        sleep=asyncio.sleep,
        random: Random | None = None,
    ) -> None:
        self._owns_client = client is None
        self._max_retries = max_retries
        self._sleep = sleep
        self._random = random or Random()
        self.last_rate_limit: XRateLimitState | None = None
        self._client = client or httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=httpx.Timeout(
                timeout_seconds,
                connect=min(timeout_seconds, 10.0),
            ),
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
                        "created_at",
                        "protected",
                        "verified",
                        "verified_type",
                        "profile_image_url",
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
            "tweet.fields": self._tweet_fields(),
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

    async def get_posts_window(
        self,
        x_user_id: str,
        *,
        start_time: datetime,
        end_time: datetime,
        max_posts: int,
    ) -> list[XPost]:
        posts: list[XPost] = []
        next_token: str | None = None
        seen_tokens: set[str] = set()
        while len(posts) < max_posts:
            page_size = max(5, min(100, max_posts - len(posts)))
            params: dict[str, Any] = {
                "max_results": page_size,
                "exclude": "retweets",
                "tweet.fields": self._tweet_fields(),
                "expansions": "attachments.media_keys",
                "media.fields": "public_metrics,type",
                "start_time": _format_x_datetime(start_time),
                "end_time": _format_x_datetime(end_time),
            }
            if next_token is not None:
                params["pagination_token"] = next_token
            payload = await self._request("GET", f"/users/{x_user_id}/tweets", params=params)
            media_by_key = {
                media["media_key"]: media
                for media in payload.get("includes", {}).get("media", [])
                if isinstance(media, dict) and "media_key" in media
            }
            for item in payload.get("data", []) or []:
                if isinstance(item, dict):
                    post = self._parse_post(item, media_by_key)
                    if start_time <= post.created_at <= end_time:
                        posts.append(post)
                    if len(posts) >= max_posts:
                        break
            meta = payload.get("meta") or {}
            next_token = meta.get("next_token")
            if not isinstance(next_token, str) or next_token in seen_tokens:
                break
            seen_tokens.add(next_token)
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
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.request(method, path, params=params)
            except httpx.TimeoutException as exc:
                last_error = exc
                if attempt >= self._max_retries:
                    raise XProviderError("X API request timed out.") from exc
                await self._sleep_for_retry(attempt)
                continue
            except httpx.HTTPError as exc:
                raise XProviderError("X API request failed before receiving a response.") from exc

            self._record_rate_limit(response)
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
                if attempt >= self._max_retries:
                    raise last_error
                await self._sleep_for_retry(attempt)
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

    async def _sleep_for_retry(self, attempt: int) -> None:
        delay = min(30.0, (2**attempt) + self._random.random())
        result = self._sleep(delay)
        if isawaitable(result):
            await result

    def _record_rate_limit(self, response: httpx.Response) -> None:
        self.last_rate_limit = XRateLimitState(
            limit=_parse_int_header(response.headers.get("x-rate-limit-limit")),
            remaining=_parse_int_header(response.headers.get("x-rate-limit-remaining")),
            reset_epoch=_parse_int_header(response.headers.get("x-rate-limit-reset")),
        )

    def _parse_account(self, data: dict[str, Any]) -> XAccount:
        if not isinstance(data.get("id"), str) or not isinstance(data.get("username"), str):
            raise XMalformedResponseError("X API user response did not include id and username.")
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
            profile_image_url=data.get("profile_image_url"),
            created_at=parse_x_datetime(data["created_at"]) if data.get("created_at") else None,
            verified_type=data.get("verified_type"),
            raw=data,
        )

    def _parse_post(self, data: dict[str, Any], media_by_key: dict[str, dict[str, Any]]) -> XPost:
        if not isinstance(data.get("id"), str) or not isinstance(data.get("created_at"), str):
            raise XMalformedResponseError("X API post response did not include id and created_at.")
        public_metrics = data.get("public_metrics") or {}
        video_view_count = None
        for media_key in data.get("attachments", {}).get("media_keys", []) or []:
            media_metrics = (media_by_key.get(media_key) or {}).get("public_metrics") or {}
            media_view_count = media_metrics.get("view_count")
            if media_view_count is not None:
                video_view_count = (video_view_count or 0) + media_view_count

        post_id = str(data["id"])
        author_id = str(data.get("author_id") or "")
        post_type, referenced_post_id = _post_type(data.get("referenced_tweets") or [])
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
            post_type=post_type,
            referenced_post_id=referenced_post_id,
            conversation_id=data.get("conversation_id"),
            lang=data.get("lang"),
            possibly_sensitive=data.get("possibly_sensitive"),
            raw=data,
        )

    def _tweet_fields(self) -> str:
        return ",".join(
            [
                "id",
                "text",
                "author_id",
                "created_at",
                "public_metrics",
                "attachments",
                "conversation_id",
                "lang",
                "possibly_sensitive",
                "referenced_tweets",
            ]
        )


def _parse_int_header(value: str | None) -> int | None:
    if value is None or not value.isdigit():
        return None
    return int(value)


def _format_x_datetime(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _post_type(referenced_tweets: list[Any]) -> tuple[str, str | None]:
    if not referenced_tweets:
        return "post", None
    first = referenced_tweets[0]
    if not isinstance(first, dict):
        return "post", None
    reference_type = first.get("type")
    reference_id = first.get("id")
    if reference_type == "quoted":
        return "quote", reference_id if isinstance(reference_id, str) else None
    if reference_type == "replied_to":
        return "reply", reference_id if isinstance(reference_id, str) else None
    if reference_type == "retweeted":
        return "repost", reference_id if isinstance(reference_id, str) else None
    return "post", reference_id if isinstance(reference_id, str) else None
