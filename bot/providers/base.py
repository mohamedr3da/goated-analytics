from __future__ import annotations

from typing import Protocol

from bot.providers.types import XAccount, XPost


class XProviderError(Exception):
    """Base error raised by an X analytics provider."""


class XAuthError(XProviderError):
    """Authentication or authorization failed."""


class XNotFoundError(XProviderError):
    """Requested X resource was not found."""


class XRateLimitError(XProviderError):
    def __init__(self, message: str, *, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class XAnalyticsProvider(Protocol):
    async def get_account_by_username(self, username: str) -> XAccount:
        raise NotImplementedError

    async def get_recent_posts(
        self,
        x_user_id: str,
        *,
        max_results: int,
        since_id: str | None = None,
    ) -> list[XPost]:
        raise NotImplementedError

    async def health_check(self) -> bool:
        raise NotImplementedError

    async def aclose(self) -> None:
        return None

