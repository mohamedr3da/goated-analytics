from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import AccountSnapshot, Post, TrackedAccount
from bot.providers.base import XAnalyticsProvider
from bot.repositories.accounts import AccountRepository
from bot.repositories.posts import PostRepository
from bot.utils.time import utcnow
from bot.utils.usernames import normalize_x_username


@dataclass(frozen=True)
class AccountSummary:
    username: str
    display_name: str
    followers_count: int
    post_count: int
    tracked_posts: int
    tracking_started_at: datetime


@dataclass(frozen=True)
class TrackResult:
    account: TrackedAccount
    posts_imported: int
    metric_snapshots_written: int
    captured_at: datetime


class TrackingService:
    def __init__(self, session: AsyncSession, provider: XAnalyticsProvider) -> None:
        self.session = session
        self.provider = provider
        self.accounts = AccountRepository(session)
        self.posts = PostRepository(session)

    async def track(
        self,
        username: str,
        *,
        captured_at: datetime | None = None,
        backfill_days: int = 30,
        backfill_max_posts: int = 200,
    ) -> TrackResult:
        captured_at = captured_at or utcnow()
        normalized = normalize_x_username(username)
        account_payload = await self.provider.get_account_by_username(normalized)
        account = await self.accounts.upsert_tracked_account(account_payload)
        await self.accounts.record_account_snapshot(account, account_payload, captured_at)
        posts_imported = 0
        snapshots_written = 0
        backfill_posts = await self.provider.get_posts_window(
            account.x_user_id,
            start_time=captured_at - timedelta(days=backfill_days),
            end_time=captured_at,
            max_posts=backfill_max_posts,
        )
        for post_payload in backfill_posts:
            post = await self.posts.upsert_post(account, post_payload)
            snapshot = await self.posts.record_metric_snapshot(
                post,
                post_payload.metrics,
                captured_at,
            )
            if snapshot.captured_at == captured_at:
                snapshots_written += 1
            posts_imported += 1
        await self.accounts.mark_refresh_success(account, captured_at)
        return TrackResult(
            account=account,
            posts_imported=posts_imported,
            metric_snapshots_written=snapshots_written,
            captured_at=captured_at,
        )

    async def untrack(self, username: str) -> TrackedAccount | None:
        return await self.accounts.disable_tracking(username)

    async def current_summary(self, username: str) -> AccountSummary | None:
        account = await self.accounts.get_by_username(username)
        if account is None:
            return None
        latest_snapshot = await self.session.scalar(
            select(AccountSnapshot)
            .where(AccountSnapshot.account_id == account.id)
            .order_by(AccountSnapshot.captured_at.desc())
            .limit(1)
        )
        post_count = await self.session.scalar(
            select(func.count(Post.id)).where(Post.account_id == account.id)
        )
        return AccountSummary(
            username=account.username,
            display_name=account.display_name,
            followers_count=latest_snapshot.followers_count if latest_snapshot else 0,
            post_count=latest_snapshot.post_count if latest_snapshot else 0,
            tracked_posts=int(post_count or 0),
            tracking_started_at=account.tracking_started_at,
        )
