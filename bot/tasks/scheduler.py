from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.providers.base import XAnalyticsProvider
from bot.tasks.collector import CollectionService

logger = logging.getLogger(__name__)


class CollectorScheduler:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        provider: XAnalyticsProvider,
        interval_minutes: int,
        recent_posts_limit: int,
    ) -> None:
        self.session_factory = session_factory
        self.provider = provider
        self.interval_seconds = interval_minutes * 60
        self.recent_posts_limit = recent_posts_limit
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self.last_result = None

    @property
    def status_label(self) -> str:
        if self._task is None:
            return "Stopped"
        if self._task.done():
            return "Stopped"
        return "Running"

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop_event.clear()
            self._task = asyncio.create_task(self._run(), name="x-analytics-collector")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                async with self.session_factory() as session:
                    self.last_result = await CollectionService(
                        session=session,
                        provider=self.provider,
                        recent_posts_limit=self.recent_posts_limit,
                    ).collect_all()
                logger.info("collection_finished", extra={"result": self.last_result})
            except Exception as exc:
                logger.exception("collection_cycle_failed", extra={"error": str(exc)})
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.interval_seconds)
            except TimeoutError:
                continue

