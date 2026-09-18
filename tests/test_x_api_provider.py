from datetime import UTC, datetime

import httpx
import pytest

from bot.providers.base import (
    XAuthError,
    XMalformedResponseError,
    XNotFoundError,
    XProviderError,
    XRateLimitError,
)
from bot.providers.x_api import XApiProvider


@pytest.mark.asyncio
async def test_x_api_provider_parses_public_account_and_post_metrics() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/2/users/by/username/OpenAI":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "id": "42",
                        "username": "OpenAI",
                        "name": "OpenAI",
                        "protected": False,
                        "verified": True,
                        "public_metrics": {
                            "followers_count": 10,
                            "following_count": 2,
                            "post_count": 3,
                            "listed_count": 4,
                        },
                    }
                },
            )
        if request.url.path == "/2/users/42/tweets":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "99",
                            "author_id": "42",
                            "created_at": "2026-09-18T08:00:00Z",
                            "text": "hello",
                            "conversation_id": "conversation-1",
                            "lang": "en",
                            "possibly_sensitive": False,
                            "referenced_tweets": [{"type": "quoted", "id": "88"}],
                            "attachments": {"media_keys": ["media-1"]},
                            "public_metrics": {
                                "impression_count": 123,
                                "like_count": 10,
                                "reply_count": 1,
                                "retweet_count": 2,
                                "quote_count": 3,
                                "bookmark_count": 4,
                            },
                        }
                    ],
                    "includes": {
                        "media": [
                            {
                                "media_key": "media-1",
                                "type": "video",
                                "public_metrics": {"view_count": 50},
                            }
                        ]
                    },
                },
            )
        return httpx.Response(404)

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.x.com/2",
    )
    provider = XApiProvider("token", client=client)

    account = await provider.get_account_by_username("@OpenAI")
    posts = await provider.get_recent_posts("42", max_results=5)

    assert account.id == "42"
    assert account.followers_count == 10
    assert posts[0].created_at == datetime(2026, 9, 18, 8, 0, tzinfo=UTC)
    assert posts[0].metrics.impression_count == 123
    assert posts[0].metrics.repost_count == 2
    assert posts[0].metrics.video_view_count == 50
    assert posts[0].post_type == "quote"
    assert posts[0].conversation_id == "conversation-1"
    await client.aclose()


@pytest.mark.asyncio
async def test_x_api_provider_raises_rate_limit_with_retry_after() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(429, headers={"retry-after": "12"})
        ),
        base_url="https://api.x.com/2",
    )
    provider = XApiProvider("token", client=client)

    with pytest.raises(XRateLimitError) as exc_info:
        await provider.get_account_by_username("OpenAI")

    assert exc_info.value.retry_after_seconds == 12
    assert provider.last_rate_limit is not None
    assert provider.last_rate_limit.remaining is None
    await client.aclose()


@pytest.mark.asyncio
async def test_x_api_provider_tracks_rate_limit_headers_on_success() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                headers={
                    "x-rate-limit-limit": "15",
                    "x-rate-limit-remaining": "14",
                    "x-rate-limit-reset": "1790000000",
                },
                json={
                    "data": {
                        "id": "42",
                        "username": "OpenAI",
                        "name": "OpenAI",
                        "public_metrics": {},
                    }
                },
            )
        ),
        base_url="https://api.x.com/2",
    )
    provider = XApiProvider("token", client=client)

    await provider.get_account_by_username("OpenAI")

    assert provider.last_rate_limit is not None
    assert provider.last_rate_limit.limit == 15
    assert provider.last_rate_limit.remaining == 14
    assert provider.last_rate_limit.reset_epoch == 1_790_000_000
    await client.aclose()


@pytest.mark.asyncio
async def test_x_api_provider_paginates_posts_until_window_or_cap() -> None:
    seen_tokens: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        token = request.url.params.get("pagination_token")
        seen_tokens.append(token or None)
        if token is None:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "101",
                            "author_id": "42",
                            "created_at": "2026-09-18T08:00:00Z",
                            "text": "new",
                            "public_metrics": {"impression_count": 10},
                        }
                    ],
                    "meta": {"next_token": "next-page"},
                },
            )
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "100",
                        "author_id": "42",
                        "created_at": "2026-09-17T08:00:00Z",
                        "text": "older",
                        "public_metrics": {"impression_count": 20},
                    }
                ],
                "meta": {},
            },
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.x.com/2",
    )
    provider = XApiProvider("token", client=client)

    posts = await provider.get_posts_window(
        "42",
        start_time=datetime(2026, 9, 17, 0, 0, tzinfo=UTC),
        end_time=datetime(2026, 9, 19, 0, 0, tzinfo=UTC),
        max_posts=2,
    )

    assert [post.id for post in posts] == ["101", "100"]
    assert seen_tokens == [None, "next-page"]
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "exception_type"),
    [
        (401, XAuthError),
        (403, XAuthError),
        (404, XNotFoundError),
    ],
)
async def test_x_api_provider_maps_permanent_http_errors(
    status_code: int,
    exception_type: type[Exception],
) -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(status_code)),
        base_url="https://api.x.com/2",
    )
    provider = XApiProvider("token", client=client)

    with pytest.raises(exception_type):
        await provider.get_account_by_username("OpenAI")

    await client.aclose()


@pytest.mark.asyncio
async def test_x_api_provider_retries_transient_server_errors() -> None:
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(500)
        return httpx.Response(
            200,
            json={
                "data": {
                    "id": "42",
                    "username": "OpenAI",
                    "name": "OpenAI",
                    "public_metrics": {},
                }
            },
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.x.com/2",
    )
    provider = XApiProvider("token", client=client, sleep=lambda _seconds: None)

    account = await provider.get_account_by_username("OpenAI")

    assert account.id == "42"
    assert attempts == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_x_api_provider_rejects_malformed_user_payload() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={"data": {}})),
        base_url="https://api.x.com/2",
    )
    provider = XApiProvider("token", client=client)

    with pytest.raises(XMalformedResponseError):
        await provider.get_account_by_username("OpenAI")

    await client.aclose()


@pytest.mark.asyncio
async def test_x_api_provider_wraps_timeouts() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("boom")

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.x.com/2",
    )
    provider = XApiProvider("token", client=client, sleep=lambda _seconds: None, max_retries=1)

    with pytest.raises(XProviderError, match="timed out"):
        await provider.get_account_by_username("OpenAI")

    await client.aclose()
