from __future__ import annotations

import html as html_lib
import json
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from bot.providers.scraper.errors import (
    AccountNotFound,
    LoginRequired,
    ParseFailure,
    UnexpectedPage,
)
from bot.providers.scraper.models import ScrapedPost, ScrapedProfile, ScrapeResult, ScrapeStats
from bot.providers.types import XPostMetrics
from bot.utils.usernames import normalize_x_username

_META_RE = re.compile(
    r"<meta\s+(?P<attrs>[^>]*?)>",
    re.IGNORECASE | re.DOTALL,
)
_ATTR_RE = re.compile(
    r"(?P<name>[a-zA-Z_:.-]+)\s*=\s*(?P<quote>['\"])(?P<value>.*?)(?P=quote)",
    re.DOTALL,
)
_STRING_RE = r'"((?:\\.|[^"\\])*)"'


def parse_public_count(value: str | None) -> int | None:
    if value is None:
        return None
    normalized = html_lib.unescape(value).strip()
    if not normalized or normalized.lower() in {"unavailable", "n/a", "none", "-"}:
        return None
    normalized = normalized.replace(",", "").replace(" ", "")
    suffix = normalized[-1:].upper()
    multiplier = Decimal(1)
    if suffix in {"K", "M", "B"}:
        normalized = normalized[:-1]
        multiplier = {"K": Decimal(1_000), "M": Decimal(1_000_000), "B": Decimal(1_000_000_000)}[
            suffix
        ]
    try:
        return int(Decimal(normalized) * multiplier)
    except (InvalidOperation, ValueError):
        return None


def parse_public_profile_page(
    html: str,
    *,
    requested_username: str,
    max_posts: int = 10,
) -> ScrapeResult:
    _raise_for_known_failure(html)
    records = _extract_records(html)
    meta = _extract_meta(html)
    profile = _parse_profile(html, records, meta, requested_username)
    posts = _parse_posts(records, profile, max_posts=max_posts)
    if profile.x_user_id == "" and not posts:
        raise ParseFailure("Public X page did not contain profile or timeline records.")
    stats = _stats_for_posts(posts)
    return ScrapeResult(profile=profile, posts=posts, stats=stats)


def _raise_for_known_failure(html: str) -> None:
    lowered = html.lower()
    if "this account doesn't exist" in lowered or "this account does not exist" in lowered:
        raise AccountNotFound("X account was not found.")
    if "account suspended" in lowered:
        raise AccountNotFound("X account is suspended or unavailable.")
    if "log in to x" in lowered or "sign in to x" in lowered:
        raise LoginRequired("X public page requires login.")


def _extract_meta(html: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    for match in _META_RE.finditer(html):
        attrs = {
            item.group("name").lower(): html_lib.unescape(item.group("value"))
            for item in _ATTR_RE.finditer(match.group("attrs"))
        }
        key = attrs.get("property") or attrs.get("name")
        content = attrs.get("content")
        if key and content:
            meta[key] = content
    return meta


def _extract_records(text: str) -> dict[str, str]:
    records: dict[str, str] = {}
    for marker in re.finditer(r'__typename:"', text):
        start = text.rfind("{", 0, marker.start())
        if start == -1:
            continue
        end = _find_matching_brace(text, start)
        if end is None:
            continue
        body = text[start + 1 : end]
        record_id = _extract_js_string(body, "__id")
        if record_id:
            records[record_id] = body
    return records


def _find_matching_brace(text: str, start: int) -> int | None:
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    return None


def _parse_profile(
    html: str,
    records: dict[str, str],
    meta: dict[str, str],
    requested_username: str,
) -> ScrapedProfile:
    normalized = normalize_x_username(requested_username)
    user_body = next((body for body in records.values() if '__typename:"User"' in body), "")
    core = records.get(_extract_ref(user_body, "core") or "", "")
    relationship = records.get(_extract_ref(user_body, "relationship_counts") or "", "")
    tweet_counts = records.get(_extract_ref(user_body, "tweet_counts") or "", "")
    avatar = records.get(_extract_ref(user_body, "avatar") or "", "")
    verification = records.get(_extract_ref(user_body, "verification") or "", "")

    x_user_id = _extract_js_string(user_body, "rest_id") or _extract_js_string(html, "restId") or ""
    username = (
        _extract_js_string(core, "screen_name")
        or _extract_js_string(html, "screenName")
        or meta.get("profile:username")
        or normalized
    )
    display_name = (
        _extract_js_string(core, "name")
        or _extract_js_string(html, "name")
        or meta.get("profile:first_name")
        or username
    )
    created_at_ms = _extract_js_int(core, "created_at_ms") or _extract_js_int(html, "createdAtMs")
    created_at = (
        datetime.fromtimestamp(created_at_ms / 1000, UTC)
        if created_at_ms is not None
        else None
    )
    followers = _extract_js_int(relationship, "followers") or _extract_js_int(html, "followers")
    following = _extract_js_int(relationship, "following") or _extract_js_int(html, "following")
    post_count = (
        _extract_js_int(tweet_counts, "tweets")
        or _extract_js_int(html, "tweets")
        or _meta_posts(meta)
    )
    profile_image = (
        _extract_js_string(avatar, "image_url")
        or _extract_js_string(html, "avatarUrl")
        or meta.get("og:image")
    )
    blue_verified = _extract_js_bool(verification, "is_blue_verified")
    verified = _extract_js_bool(verification, "verified") or _extract_js_bool(html, "isVerified")
    verified_type = _extract_js_string(verification, "verified_type")
    if blue_verified:
        verified = True
        verified_type = verified_type or "blue"
    if not x_user_id and not username:
        raise UnexpectedPage("Public X profile fields were not found.")
    return ScrapedProfile(
        x_user_id=x_user_id,
        username=username,
        display_name=display_name,
        protected=_extract_js_bool(html, "protected") or False,
        verified=bool(verified),
        followers_count=followers,
        following_count=following,
        post_count=post_count,
        listed_count=None,
        profile_image_url=profile_image,
        created_at=created_at,
        verified_type=verified_type,
        raw={
            "provider": "public_scraper",
            "meta_joined": (
                meta.get("twitter:data2") if meta.get("twitter:label2") == "Joined" else None
            ),
        },
    )


def _meta_posts(meta: dict[str, str]) -> int | None:
    for index in range(1, 5):
        if meta.get(f"twitter:label{index}") == "Posts":
            return parse_public_count(meta.get(f"twitter:data{index}"))
    return None


def _parse_posts(
    records: dict[str, str],
    profile: ScrapedProfile,
    *,
    max_posts: int,
) -> list[ScrapedPost]:
    if max_posts <= 0:
        return []
    posts: list[ScrapedPost] = []
    seen: set[str] = set()
    for body in records.values():
        if '__typename:"Tweet"' not in body:
            continue
        post_id = _extract_js_string(body, "rest_id")
        if not post_id or post_id in seen:
            continue
        details = records.get(_extract_ref(body, "details") or "", "")
        created_at_ms = _extract_js_int(details, "created_at_ms")
        text = _extract_js_string(details, "full_text")
        if created_at_ms is None or text is None:
            continue
        counts = records.get(_extract_ref(body, "counts") or "", "")
        views = records.get(_extract_ref(body, "views") or "", "")
        legacy = records.get(_extract_ref(body, "legacy") or "", "")
        metrics = XPostMetrics(
            impression_count=parse_public_count(_extract_js_string(views, "count")),
            like_count=_extract_js_int(counts, "favorite_count"),
            reply_count=_extract_js_int(counts, "reply_count"),
            repost_count=_extract_js_int(counts, "retweet_count"),
            quote_count=_extract_js_int(counts, "quote_count"),
            bookmark_count=_extract_js_int(counts, "bookmark_count"),
            video_view_count=None,
            raw={"provider": "public_scraper"},
        )
        post_type = _post_type(body, legacy)
        posts.append(
            ScrapedPost(
                id=post_id,
                author_id=profile.x_user_id,
                created_at=datetime.fromtimestamp(created_at_ms / 1000, UTC),
                text=text,
                url=f"https://x.com/{profile.username}/status/{post_id}",
                metrics=metrics,
                post_type=post_type,
                lang=_extract_js_string(legacy, "lang"),
                possibly_sensitive=_extract_js_bool(legacy, "possibly_sensitive"),
                raw={"provider": "public_scraper"},
            )
        )
        seen.add(post_id)
        if len(posts) >= max_posts:
            break
    return posts


def _post_type(tweet_body: str, legacy_body: str) -> str:
    if _field_non_null(legacy_body, "retweeted_status_results"):
        return "repost"
    if _field_non_null(tweet_body, "quoted_tweet_results"):
        return "quote"
    if _field_non_null(tweet_body, "reply_to_results"):
        return "reply"
    return "post"


def _stats_for_posts(posts: list[ScrapedPost]) -> ScrapeStats:
    metrics_extracted = 0
    missing_metrics = 0
    for post in posts:
        values = [
            post.metrics.impression_count,
            post.metrics.like_count,
            post.metrics.reply_count,
            post.metrics.repost_count,
            post.metrics.quote_count,
            post.metrics.bookmark_count,
        ]
        metrics_extracted += sum(value is not None for value in values)
        missing_metrics += sum(value is None for value in values)
    return ScrapeStats(
        posts_extracted=len(posts),
        metrics_extracted=metrics_extracted,
        missing_metrics=missing_metrics,
    )


def _extract_ref(body: str, field: str) -> str | None:
    match = re.search(
        rf"(?<![A-Za-z0-9_]){re.escape(field)}:\$R\[\d+\]=\{{__ref:{_STRING_RE}\}}",
        body,
    )
    return _decode_js_string(match.group(1)) if match else None


def _extract_js_string(body: str, field: str) -> str | None:
    match = re.search(rf"(?<![A-Za-z0-9_]){re.escape(field)}:{_STRING_RE}", body)
    if not match:
        return None
    return _decode_js_string(match.group(1))


def _decode_js_string(value: str) -> str:
    try:
        return html_lib.unescape(json.loads(f'"{value}"'))
    except json.JSONDecodeError:
        return html_lib.unescape(value)


def _extract_js_int(body: str, field: str) -> int | None:
    match = re.search(rf"(?<![A-Za-z0-9_]){re.escape(field)}:(?P<value>-?\d+|null)", body)
    if not match or match.group("value") == "null":
        return None
    return int(match.group("value"))


def _extract_js_bool(body: str, field: str) -> bool | None:
    match = re.search(
        rf"(?<![A-Za-z0-9_]){re.escape(field)}:(?P<value>!0|!1|true|false|null)",
        body,
    )
    if not match or match.group("value") == "null":
        return None
    return match.group("value") in {"!0", "true"}


def _field_non_null(body: str, field: str) -> bool:
    match = re.search(
        rf"(?<![A-Za-z0-9_]){re.escape(field)}:(?P<value>null|\$R\[\d+\]=\{{__ref:{_STRING_RE}\}})",
        body,
    )
    return bool(match and match.group("value") != "null")
