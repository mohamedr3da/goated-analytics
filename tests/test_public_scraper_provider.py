from __future__ import annotations

import httpx
import pytest

from bot.providers.public_scraper import PublicScraperProvider


def _profile_html() -> str:
    user_ref = "VXNlcjoxMjM="
    return f"""
    <html><body>
      {user_ref}:$R[15]={{__id:"{user_ref}",__typename:"User",rest_id:"1688946553875058689",
        core:$R[17]={{__ref:"client:{user_ref}:core"}},
        tweet_counts:$R[19]={{__ref:"client:{user_ref}:tweet_counts"}},
        relationship_counts:$R[25]={{__ref:"client:{user_ref}:relationship_counts"}},
        verification:$R[26]={{__ref:"client:{user_ref}:verification"}}}},
      "client:{user_ref}:core":$R[32]={{__id:"client:{user_ref}:core",__typename:"UserCore",
        name:"Rawdogmoon",screen_name:"rawdogmoon",created_at_ms:1691511227184}},
      "client:{user_ref}:tweet_counts":$R[34]={{__id:"client:{user_ref}:tweet_counts",
        __typename:"UserTweetCounts",tweets:611}},
      "client:{user_ref}:relationship_counts":$R[49]={{__id:"client:{user_ref}:relationship_counts",
        __typename:"UserRelationshipCounts",followers:11030,following:290}},
      "client:{user_ref}:verification":$R[50]={{__id:"client:{user_ref}:verification",
        __typename:"UserVerification",verified:!1,is_blue_verified:!0,verified_type:null}}
    </body></html>
    """


def _post_html() -> str:
    post_id = "2100698123983347787"
    post_ref = f"VHdlZXQ6{post_id}"
    return f"""
      "{post_ref}":$R[100]={{__id:"{post_ref}",__typename:"Tweet",rest_id:"{post_id}",
        counts:$R[102]={{__ref:"client:{post_ref}:counts"}},
        views:$R[103]={{__ref:"client:{post_ref}:views"}},
        legacy:$R[104]={{__ref:"client:{post_ref}:legacy"}},
        details:$R[105]={{__ref:"client:{post_ref}:details"}}}},
      "client:{post_ref}:counts":$R[108]={{__id:"client:{post_ref}:counts",__typename:"ApiCounts",
        reply_count:4,retweet_count:5,favorite_count:1200,quote_count:2,bookmark_count:9}},
      "client:{post_ref}:views":$R[109]={{__id:"client:{post_ref}:views",__typename:"ViewCountInfo",
        count:"98765"}},
      "client:{post_ref}:legacy":$R[110]={{__id:"client:{post_ref}:legacy",__typename:"LegacyTweet",
        retweeted_status_results:null,possibly_sensitive:null,lang:"en"}},
      "client:{post_ref}:details":$R[111]={{__id:"client:{post_ref}:details",__typename:"TBirdData",
        full_text:"I like provider tests.",created_at_ms:1789730000000}}
    """


@pytest.mark.asyncio
async def test_public_scraper_provider_maps_html_and_does_not_persist_cookies() -> None:
    html = _profile_html() + _post_html()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            headers={"set-cookie": "guest_id=v1%3Aexample; Path=/; Secure; HttpOnly"},
            text=html,
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://x.com",
    )
    provider = PublicScraperProvider(client=client)

    account = await provider.get_account_by_username("@rawdogmoon")
    posts = await provider.get_recent_posts(account.id, max_results=10)

    assert account.id == "1688946553875058689"
    assert account.followers_count == 11030
    assert posts[0].metrics.impression_count == 98765
    assert posts[0].metrics.video_view_count is None
    assert len(requests) == 1
    assert list(client.cookies.jar) == []
    await client.aclose()
