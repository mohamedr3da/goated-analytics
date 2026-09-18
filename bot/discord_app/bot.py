from __future__ import annotations

import discord
from discord.ext import commands
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.config.settings import Settings
from bot.discord_app.commands import register_commands
from bot.providers.base import XAnalyticsProvider
from bot.tasks.scheduler import CollectorScheduler


def build_bot(
    *,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    provider: XAnalyticsProvider,
    scheduler: CollectorScheduler,
) -> commands.Bot:
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix=commands.when_mentioned, intents=intents)
    register_commands(
        bot=bot,
        settings=settings,
        session_factory=session_factory,
        provider=provider,
        scheduler=scheduler,
    )
    return bot

