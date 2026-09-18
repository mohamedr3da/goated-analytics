from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot.providers.public_scraper import PublicScraperProvider


def _post_payload(post: Any) -> dict[str, Any]:
    metrics = post.metrics
    return {
        "id": post.id,
        "created_at": post.created_at.isoformat(),
        "type": post.post_type,
        "url": post.url,
        "text_preview": post.text[:160],
        "metrics": {
            "post_impressions": metrics.impression_count,
            "likes": metrics.like_count,
            "replies": metrics.reply_count,
            "reposts": metrics.repost_count,
            "quotes": metrics.quote_count,
            "bookmarks": metrics.bookmark_count,
            "video_or_media_views": metrics.video_view_count,
        },
    }


async def _probe(username: str, max_posts: int) -> dict[str, Any]:
    provider = PublicScraperProvider(recent_post_limit=max_posts)
    started_at = time.perf_counter()
    try:
        account = await provider.get_account_by_username(username)
        posts = await provider.get_recent_posts(account.id, max_results=max_posts)
        duration_seconds = time.perf_counter() - started_at
        return {
            "username": account.username,
            "x_user_id": account.id,
            "display_name": account.display_name,
            "followers_count": account.followers_count,
            "following_count": account.following_count,
            "post_count": account.post_count,
            "listed_count": account.listed_count,
            "verified": account.verified,
            "verified_type": account.verified_type,
            "profile_image_url_present": account.profile_image_url is not None,
            "created_at": account.created_at.isoformat() if account.created_at else None,
            "posts_returned": len(posts),
            "posts": [_post_payload(post) for post in posts],
            "duration_seconds": round(duration_seconds, 3),
            "auth": "none",
            "browser": "none",
            "cookies_persisted": False,
            "stats": provider.last_scrape_stats,
        }
    finally:
        await provider.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a local public X scraper proof.")
    parser.add_argument("username", nargs="?", default="rawdogmoon")
    parser.add_argument("--max-posts", type=int, default=10)
    args = parser.parse_args()

    payload = asyncio.run(_probe(args.username, args.max_posts))
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
