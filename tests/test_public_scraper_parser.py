from __future__ import annotations

from datetime import UTC, datetime

import pytest

from bot.providers.scraper.errors import AccountNotFound, LoginRequired, ParseFailure
from bot.providers.scraper.parser import parse_public_count, parse_public_profile_page

USER_REF = "VXNlcjoxMjM="


def profile_record() -> str:
    return f"""
    <html><head>
      <meta property="profile:username" content="rawdogmoon" />
      <meta property="og:image" content="https://pbs.twimg.com/profile.jpg" />
      <meta name="twitter:label1" content="Posts" />
      <meta name="twitter:data1" content="611" />
    </head><body>
      dehydratedData:$R[9]={{relayRecords:$R[10]={{
        {USER_REF}:$R[15]={{__id:"{USER_REF}",__typename:"User",rest_id:"1688946553875058689",
          core:$R[17]={{__ref:"client:{USER_REF}:core"}},
          tweet_counts:$R[19]={{__ref:"client:{USER_REF}:tweet_counts"}},
          avatar:$R[21]={{__ref:"client:{USER_REF}:avatar"}},
          relationship_counts:$R[25]={{__ref:"client:{USER_REF}:relationship_counts"}},
          verification:$R[26]={{__ref:"client:{USER_REF}:verification"}}}},
        "client:{USER_REF}:core":$R[32]={{__id:"client:{USER_REF}:core",__typename:"UserCore",
          name:"Rawdogmoon",screen_name:"rawdogmoon",created_at_ms:1691511227184}},
        "client:{USER_REF}:tweet_counts":$R[34]={{__id:"client:{USER_REF}:tweet_counts",
          __typename:"UserTweetCounts",tweets:611}},
        "client:{USER_REF}:avatar":$R[36]={{__id:"client:{USER_REF}:avatar",
          __typename:"UserAvatar",image_url:"https://pbs.twimg.com/profile_normal.jpg"}},
        "client:{USER_REF}:relationship_counts":$R[49]={{__id:"client:{USER_REF}:relationship_counts",
          __typename:"UserRelationshipCounts",followers:11030,following:290}},
        "client:{USER_REF}:verification":$R[50]={{__id:"client:{USER_REF}:verification",
          __typename:"UserVerification",verified:!1,is_blue_verified:!0,verified_type:null}}
      }}}}
    """


def tweet_record(
    post_id: str,
    *,
    text: str = "I like parser tests.",
    created_at_ms: int = 1789730000000,
    replies: int | None = 4,
    reposts: int | None = 5,
    likes: int | None = 1200,
    quotes: int | None = 2,
    bookmarks: int | None = 9,
    views: str | None = "98765",
    reply: bool = False,
    quote: bool = False,
    repost: bool = False,
) -> str:
    post_ref = f"VHdlZXQ6{post_id}"
    reply_ref = "$R[1]={__ref:\"reply\"}" if reply else "null"
    quote_ref = "$R[2]={__ref:\"quote\"}" if quote else "null"
    repost_ref = "$R[3]={__ref:\"repost\"}" if repost else "null"
    view_payload = "count:null" if views is None else f'count:"{views}"'
    return f"""
      "{post_ref}":$R[100]={{__id:"{post_ref}",__typename:"Tweet",rest_id:"{post_id}",
        core:$R[101]={{__ref:"client:{post_ref}:core"}},
        reply_to_results:{reply_ref},
        quoted_tweet_results:{quote_ref},
        counts:$R[102]={{__ref:"client:{post_ref}:counts"}},
        views:$R[103]={{__ref:"client:{post_ref}:views"}},
        legacy:$R[104]={{__ref:"client:{post_ref}:legacy"}},
        details:$R[105]={{__ref:"client:{post_ref}:details"}}}},
      "client:{post_ref}:core":$R[106]={{__id:"client:{post_ref}:core",__typename:"TweetCore",
        user_results:$R[107]={{__ref:"UserResults:1688946553875058689"}}}},
      "client:{post_ref}:counts":$R[108]={{__id:"client:{post_ref}:counts",__typename:"ApiCounts",
        reply_count:{_js_int(replies)},retweet_count:{_js_int(reposts)},
        favorite_count:{_js_int(likes)},quote_count:{_js_int(quotes)},bookmark_count:{_js_int(bookmarks)}}},
      "client:{post_ref}:views":$R[109]={{__id:"client:{post_ref}:views",__typename:"ViewCountInfo",
        {view_payload}}},
      "client:{post_ref}:legacy":$R[110]={{__id:"client:{post_ref}:legacy",__typename:"LegacyTweet",
        retweeted_status_results:{repost_ref},possibly_sensitive:null,lang:"en"}},
      "client:{post_ref}:details":$R[111]={{__id:"client:{post_ref}:details",__typename:"TBirdData",
        full_text:"{text}",created_at_ms:{created_at_ms}}}
    """


def _js_int(value: int | None) -> str:
    return "null" if value is None else str(value)


def test_parse_public_profile_extracts_available_profile_fields() -> None:
    result = parse_public_profile_page(profile_record(), requested_username="rawdogmoon")

    assert result.profile.username == "rawdogmoon"
    assert result.profile.display_name == "Rawdogmoon"
    assert result.profile.x_user_id == "1688946553875058689"
    assert result.profile.followers_count == 11030
    assert result.profile.following_count == 290
    assert result.profile.post_count == 611
    assert result.profile.profile_image_url == "https://pbs.twimg.com/profile_normal.jpg"
    assert result.profile.created_at == datetime.fromtimestamp(1691511227184 / 1000, UTC)
    assert result.profile.verified is True
    assert result.profile.verified_type == "blue"


def test_parse_public_profile_extracts_recent_posts_and_metrics() -> None:
    html = profile_record() + tweet_record("2100698123983347787")

    result = parse_public_profile_page(html, requested_username="rawdogmoon")

    assert len(result.posts) == 1
    post = result.posts[0]
    assert post.id == "2100698123983347787"
    assert post.url == "https://x.com/rawdogmoon/status/2100698123983347787"
    assert post.text == "I like parser tests."
    assert post.created_at == datetime.fromtimestamp(1789730000000 / 1000, UTC)
    assert post.post_type == "post"
    assert post.metrics.impression_count == 98765
    assert post.metrics.like_count == 1200
    assert post.metrics.reply_count == 4
    assert post.metrics.repost_count == 5
    assert post.metrics.quote_count == 2
    assert post.metrics.bookmark_count == 9
    assert post.metrics.video_view_count is None


def test_parse_public_profile_keeps_missing_metrics_as_none() -> None:
    html = profile_record() + tweet_record(
        "2100698123983347787",
        replies=None,
        views=None,
        bookmarks=None,
    )

    post = parse_public_profile_page(html, requested_username="rawdogmoon").posts[0]

    assert post.metrics.reply_count is None
    assert post.metrics.impression_count is None
    assert post.metrics.bookmark_count is None


def test_parse_public_profile_deduplicates_posts_and_honors_limit() -> None:
    html = (
        profile_record()
        + tweet_record("2100698123983347787")
        + tweet_record("2100698123983347787", text="duplicate")
        + tweet_record("2100698123983347788")
    )

    result = parse_public_profile_page(html, requested_username="rawdogmoon", max_posts=1)

    assert [post.id for post in result.posts] == ["2100698123983347787"]


def test_parse_public_profile_honors_zero_post_limit() -> None:
    html = profile_record() + tweet_record("2100698123983347787")

    result = parse_public_profile_page(html, requested_username="rawdogmoon", max_posts=0)

    assert result.posts == []


@pytest.mark.parametrize(
    ("post_type", "kwargs"),
    [
        ("reply", {"reply": True}),
        ("quote", {"quote": True}),
        ("repost", {"repost": True}),
    ],
)
def test_parse_public_profile_detects_post_type(post_type: str, kwargs: dict[str, bool]) -> None:
    html = profile_record() + tweet_record("2100698123983347787", **kwargs)

    post = parse_public_profile_page(html, requested_username="rawdogmoon").posts[0]

    assert post.post_type == post_type


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("1.2K", 1200),
        ("14.8K", 14800),
        ("2.3M", 2_300_000),
        ("1B", 1_000_000_000),
        ("67K", 67_000),
        ("1,234", 1234),
        ("1 234", 1234),
        ("unavailable", None),
    ],
)
def test_parse_public_count_handles_public_ui_formats(label: str, expected: int | None) -> None:
    assert parse_public_count(label) == expected


def test_parse_public_profile_detects_login_wall() -> None:
    html = "<html><title>Log in to X / X</title><body>Sign in to X</body></html>"

    with pytest.raises(LoginRequired):
        parse_public_profile_page(html, requested_username="rawdogmoon")


def test_parse_public_profile_detects_account_not_found() -> None:
    html = "<html><title>X</title><body>This account doesn't exist</body></html>"

    with pytest.raises(AccountNotFound):
        parse_public_profile_page(html, requested_username="rawdogmoon")


def test_parse_public_profile_rejects_unexpected_layout() -> None:
    with pytest.raises(ParseFailure):
        parse_public_profile_page(
            "<html><body>No useful records</body></html>",
            requested_username="x",
        )
