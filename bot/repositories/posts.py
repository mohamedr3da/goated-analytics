from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Post, PostMetricSnapshot, TrackedAccount
from bot.providers.types import XPost, XPostMetrics
from bot.utils.time import utcnow


class PostRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_post(self, account: TrackedAccount, post: XPost) -> Post:
        existing = await self.session.scalar(select(Post).where(Post.x_post_id == post.id))
        preview = _preview_text(post.text)
        if existing is None:
            existing = Post(
                x_post_id=post.id,
                account_id=account.id,
                created_at=post.created_at,
                text_preview=preview,
                url=post.url,
                raw_data=post.raw,
            )
            self.session.add(existing)
        else:
            existing.account_id = account.id
            existing.created_at = post.created_at
            existing.text_preview = preview
            existing.url = post.url
            existing.last_seen_at = utcnow()
            existing.raw_data = post.raw
        await self.session.flush()
        return existing

    async def latest_post_id_for_account(self, account: TrackedAccount) -> str | None:
        statement = (
            select(Post.x_post_id)
            .where(Post.account_id == account.id)
            .order_by(Post.created_at.desc(), Post.id.desc())
            .limit(1)
        )
        return await self.session.scalar(statement)

    async def record_metric_snapshot(
        self,
        post: Post,
        metrics: XPostMetrics,
        captured_at: datetime,
    ) -> PostMetricSnapshot:
        existing = await self.session.scalar(
            select(PostMetricSnapshot).where(
                PostMetricSnapshot.post_id == post.id,
                PostMetricSnapshot.captured_at == captured_at,
            )
        )
        if existing is not None:
            return existing
        snapshot = PostMetricSnapshot(
            post_id=post.id,
            captured_at=captured_at,
            impression_count=metrics.impression_count,
            like_count=metrics.like_count,
            reply_count=metrics.reply_count,
            repost_count=metrics.repost_count,
            quote_count=metrics.quote_count,
            bookmark_count=metrics.bookmark_count,
            video_view_count=metrics.video_view_count,
            raw_metrics=metrics.raw,
        )
        self.session.add(snapshot)
        await self.session.flush()
        return snapshot


def _preview_text(text: str, *, max_length: int = 500) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 3] + "..."
