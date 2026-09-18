from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import TrackedAccount
from bot.providers.base import XAnalyticsProvider
from bot.repositories.accounts import AccountRepository
from bot.repositories.posts import PostRepository
from bot.utils.time import utcnow

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CollectionResult:
    successes: int = 0
    failures: int = 0
    errors: list[str] = field(default_factory=list)


class CollectionService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        provider: XAnalyticsProvider,
        recent_posts_limit: int,
        snapshot_min_interval_minutes: int | None = None,
    ) -> None:
        self.session = session
        self.provider = provider
        self.recent_posts_limit = recent_posts_limit
        self.snapshot_min_interval_minutes = snapshot_min_interval_minutes
        self.accounts = AccountRepository(session)
        self.posts = PostRepository(session)

    async def collect_all(self, *, captured_at: datetime | None = None) -> CollectionResult:
        captured_at = captured_at or utcnow()
        accounts = await self.accounts.list_active()
        account_refs = [
            (account.id, account.x_user_id, account.username)
            for account in accounts
        ]
        successes = 0
        errors: list[str] = []
        for account_id, x_user_id, username in account_refs:
            try:
                account = await self.session.get(TrackedAccount, account_id)
                if account is None:
                    raise RuntimeError("Tracked account disappeared before collection.")
                await self.collect_account(account, captured_at=captured_at)
                await self.session.commit()
                successes += 1
            except Exception as exc:
                await self.session.rollback()
                errors.append(f"@{username}: {exc}")
                logger.warning(
                    "collection_account_failed",
                    extra={
                        "x_user_id": x_user_id,
                        "username": username,
                        "error": str(exc),
                    },
                )
        return CollectionResult(successes=successes, failures=len(errors), errors=errors)

    async def collect_account(
        self,
        account: TrackedAccount,
        *,
        captured_at: datetime,
    ) -> None:
        account_payload = await self.provider.get_account_by_username(account.username)
        tracked_account = await self.accounts.upsert_tracked_account(account_payload)
        await self.accounts.record_account_snapshot(tracked_account, account_payload, captured_at)
        recent_posts = await self.provider.get_recent_posts(
            tracked_account.x_user_id,
            max_results=self.recent_posts_limit,
        )
        for post_payload in recent_posts:
            post = await self.posts.upsert_post(tracked_account, post_payload)
            await self.posts.record_metric_snapshot(
                post,
                post_payload.metrics,
                captured_at,
                min_interval_minutes=self.snapshot_min_interval_minutes,
            )
        await self.accounts.mark_refresh_success(tracked_account, captured_at)
