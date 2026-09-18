from datetime import UTC, datetime

import httpx
import pytest

from bot.providers.base import XRateLimitError
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
    await client.aclose()

