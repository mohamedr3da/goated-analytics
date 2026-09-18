from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import AccountSnapshot, TrackedAccount
from bot.providers.types import XAccount
from bot.utils.time import utcnow
from bot.utils.usernames import normalize_x_username


class AccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ping(self) -> bool:
        try:
            await self.session.execute(text("SELECT 1"))
        except Exception:
            return False
        return True

    async def upsert_tracked_account(self, account: XAccount) -> TrackedAccount:
        existing = await self.get_by_x_user_id(account.id)
        if existing is None:
            existing = TrackedAccount(
                x_user_id=account.id,
                username=account.username,
                display_name=account.display_name,
                protected=account.protected,
                verified=account.verified,
                is_tracking_enabled=True,
            )
            self.session.add(existing)
        else:
            existing.username = account.username
            existing.display_name = account.display_name
            existing.protected = account.protected
            existing.verified = account.verified
            existing.is_tracking_enabled = True
            existing.updated_at = utcnow()
        await self.session.flush()
        return existing

    async def get_by_x_user_id(self, x_user_id: str) -> TrackedAccount | None:
        statement = select(TrackedAccount).where(TrackedAccount.x_user_id == x_user_id)
        return await self.session.scalar(statement)

    async def get_by_username(self, username: str) -> TrackedAccount | None:
        normalized = normalize_x_username(username).lower()
        statement = select(TrackedAccount).where(
            func.lower(TrackedAccount.username) == normalized
        )
        return await self.session.scalar(statement)

    async def list_active(self) -> list[TrackedAccount]:
        statement = (
            select(TrackedAccount)
            .where(TrackedAccount.is_tracking_enabled.is_(True))
            .order_by(TrackedAccount.username.asc())
        )
        return list((await self.session.scalars(statement)).all())

    async def disable_tracking(self, username: str) -> TrackedAccount | None:
        account = await self.get_by_username(username)
        if account is None:
            return None
        account.is_tracking_enabled = False
        account.updated_at = utcnow()
        await self.session.flush()
        return account

    async def record_account_snapshot(
        self,
        account: TrackedAccount,
        metrics: XAccount,
        captured_at: datetime,
    ) -> AccountSnapshot:
        existing = await self.session.scalar(
            select(AccountSnapshot).where(
                AccountSnapshot.account_id == account.id,
                AccountSnapshot.captured_at == captured_at,
            )
        )
        if existing is not None:
            return existing
        snapshot = AccountSnapshot(
            account_id=account.id,
            captured_at=captured_at,
            followers_count=metrics.followers_count,
            following_count=metrics.following_count,
            post_count=metrics.post_count,
            listed_count=metrics.listed_count,
            raw_metrics=metrics.raw.get("public_metrics") if metrics.raw else None,
        )
        self.session.add(snapshot)
        await self.session.flush()
        return snapshot
