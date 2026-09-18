from __future__ import annotations

import asyncio
import logging

from bot.config.settings import Settings
from bot.database.session import create_engine, create_session_factory, init_db
from bot.discord_app.bot import build_bot
from bot.providers.factory import create_provider
from bot.tasks.scheduler import CollectorScheduler
from bot.utils.logging import configure_logging


async def async_main() -> None:
    settings = Settings()
    configure_logging(settings.log_level)
    if settings.discord_token is None:
        raise RuntimeError("DISCORD_TOKEN is required to start the Discord bot.")

    engine = create_engine(settings.database_url)
    await init_db(engine)
    session_factory = create_session_factory(engine)
    provider = create_provider(settings)
    scheduler = CollectorScheduler(
        session_factory=session_factory,
        provider=provider,
        interval_minutes=settings.collection_interval_minutes,
        recent_posts_limit=settings.x_recent_posts_limit,
        snapshot_min_interval_minutes=settings.snapshot_min_interval_minutes,
    )
    bot = build_bot(
        settings=settings,
        session_factory=session_factory,
        provider=provider,
        scheduler=scheduler,
    )
    scheduler.start()
    try:
        await bot.start(settings.discord_token.get_secret_value())
    finally:
        await scheduler.stop()
        await provider.aclose()
        await engine.dispose()


def run() -> None:
    logging.getLogger(__name__).info("Starting X Discord analytics bot")
    asyncio.run(async_main())


if __name__ == "__main__":
    run()
