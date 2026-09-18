from __future__ import annotations

from datetime import UTC, datetime

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.analytics.periods import AnalyticsPeriod
from bot.analytics.service import AnalyticsService
from bot.config.settings import Settings
from bot.discord_app.permissions import can_manage_tracking
from bot.providers.base import XAnalyticsProvider, XProviderError
from bot.repositories.accounts import AccountRepository
from bot.services.tracking import TrackingService
from bot.tasks.scheduler import CollectorScheduler


def register_commands(
    *,
    bot: commands.Bot,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    provider: XAnalyticsProvider,
    scheduler: CollectorScheduler,
) -> None:
    @bot.event
    async def on_ready() -> None:
        await bot.tree.sync()

    @bot.tree.command(name="track", description="Track an X/Twitter account.")
    @app_commands.describe(username="X username, with or without @")
    async def track(interaction: discord.Interaction, username: str) -> None:
        await interaction.response.defer(ephemeral=True)
        if not can_manage_tracking(interaction, settings):
            await interaction.followup.send("You are not allowed to manage tracked accounts.")
            return
        async with session_factory() as session:
            try:
                account = await TrackingService(session, provider).track(username)
                await session.commit()
            except (ValueError, XProviderError) as exc:
                await session.rollback()
                await interaction.followup.send(f"Could not track `{username}`: {exc}")
                return
        await interaction.followup.send(
            f"Tracking @{account.username} ({account.display_name}) from now on."
        )

    @bot.tree.command(name="untrack", description="Stop tracking an X/Twitter account.")
    @app_commands.describe(username="X username, with or without @")
    async def untrack(interaction: discord.Interaction, username: str) -> None:
        await interaction.response.defer(ephemeral=True)
        if not can_manage_tracking(interaction, settings):
            await interaction.followup.send("You are not allowed to manage tracked accounts.")
            return
        async with session_factory() as session:
            stopped = await TrackingService(session, provider).untrack(username)
            await session.commit()
        if stopped is None:
            await interaction.followup.send(f"`{username}` is not currently tracked.")
            return
        await interaction.followup.send(f"Stopped tracking @{stopped.username}.")

    @bot.tree.command(name="tracked", description="List tracked X/Twitter accounts.")
    async def tracked(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        async with session_factory() as session:
            accounts = await AccountRepository(session).list_active()
        if not accounts:
            await interaction.followup.send("No accounts are being tracked yet.")
            return
        lines = [
            f"@{account.username} - tracking since {account.tracking_started_at:%d %b %Y}"
            for account in accounts
        ]
        await interaction.followup.send("\n".join(lines))

    @bot.tree.command(name="twitter", description="Show current tracked X/Twitter account info.")
    @app_commands.describe(username="Tracked X username, with or without @")
    async def twitter(interaction: discord.Interaction, username: str) -> None:
        await interaction.response.defer(ephemeral=not settings.public_analytics_enabled)
        async with session_factory() as session:
            summary = await TrackingService(session, provider).current_summary(username)
        if summary is None:
            await interaction.followup.send(f"`{username}` is not being tracked.")
            return
        embed = discord.Embed(
            title=f"@{summary.username}",
            description=summary.display_name,
            color=discord.Color.blue(),
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="Followers", value=f"{summary.followers_count:,}", inline=True)
        embed.add_field(name="Posts", value=f"{summary.post_count:,}", inline=True)
        embed.add_field(name="Tracked posts", value=f"{summary.tracked_posts:,}", inline=True)
        embed.add_field(
            name="Tracking since",
            value=summary.tracking_started_at.strftime("%d %b %Y"),
            inline=True,
        )
        await interaction.followup.send(embed=embed)

    @bot.tree.command(name="analytics", description="Show period analytics from stored snapshots.")
    @app_commands.describe(username="Tracked X username", period="24h, 1d, 7d, or 30d")
    async def analytics(
        interaction: discord.Interaction,
        username: str,
        period: str = "1d",
    ) -> None:
        await interaction.response.defer(ephemeral=not settings.public_analytics_enabled)
        try:
            analytics_period = AnalyticsPeriod.trailing(period)
        except ValueError as exc:
            await interaction.followup.send(str(exc))
            return
        async with session_factory() as session:
            account = await AccountRepository(session).get_by_username(username)
            if account is None:
                await interaction.followup.send(f"`{username}` is not being tracked.")
                return
            result = await AnalyticsService(session).summarize_account(account, analytics_period)
        if not result.available:
            await interaction.followup.send(result.reason)
            return
        embed = discord.Embed(title=f"@{account.username} analytics: {period}", color=0x1DA1F2)
        embed.add_field(name="Views gained", value=f"{result.views_gained:,}", inline=True)
        embed.add_field(name="Follower growth", value=f"{result.followers_gained:+,}", inline=True)
        embed.add_field(name="Posts published", value=str(result.posts_published), inline=True)
        embed.add_field(name="Likes gained", value=f"{result.likes_gained:,}", inline=True)
        embed.add_field(name="Reposts gained", value=f"{result.reposts_gained:,}", inline=True)
        embed.add_field(name="Replies gained", value=f"{result.replies_gained:,}", inline=True)
        await interaction.followup.send(embed=embed)

    @bot.tree.command(
        name="status",
        description="Show bot, database, scheduler, and provider status.",
    )
    async def status(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        async with session_factory() as session:
            db_ok = await AccountRepository(session).ping()
        provider_ok = await provider.health_check()
        embed = discord.Embed(title="Bot status", color=discord.Color.green())
        embed.add_field(name="Database", value="OK" if db_ok else "Unavailable", inline=True)
        embed.add_field(name="Scheduler", value=scheduler.status_label, inline=True)
        embed.add_field(
            name="X provider",
            value="OK" if provider_ok else "Unavailable",
            inline=True,
        )
        await interaction.followup.send(embed=embed)
