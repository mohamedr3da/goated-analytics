from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import AccountSnapshot, Post, TrackedAccount
from bot.providers.base import XAnalyticsProvider
from bot.repositories.accounts import AccountRepository
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


class TrackingService:
    def __init__(self, session: AsyncSession, provider: XAnalyticsProvider) -> None:
        self.session = session
        self.provider = provider
        self.accounts = AccountRepository(session)

    async def track(self, username: str) -> TrackedAccount:
        normalized = normalize_x_username(username)
        account_payload = await self.provider.get_account_by_username(normalized)
        account = await self.accounts.upsert_tracked_account(account_payload)
        await self.accounts.record_account_snapshot(account, account_payload, utcnow())
        return account

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

