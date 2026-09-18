from __future__ import annotations

from datetime import UTC, datetime

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.analytics.periods import AnalyticsPeriod
from bot.analytics.service import AnalyticsService
from bot.config.settings import Settings
from bot.discord_app.formatting import (
    compact_number,
    coverage_label,
    safe_preview,
    signed_compact_number,
)
from bot.discord_app.permissions import can_manage_tracking
from bot.providers.base import XAnalyticsProvider, XProviderError
from bot.repositories.accounts import AccountRepository
from bot.services.tracking import TrackingService
from bot.tasks.collector import CollectionService
from bot.tasks.scheduler import CollectorScheduler


def _provider_mode_label(settings: Settings) -> str:
    if settings.x_provider_mode == "scraper":
        return "scraper (public, unauthenticated)"
    if settings.x_provider_mode == "x_api":
        return "x_api (official API)"
    return "mock"


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
                account = await TrackingService(session, provider).track(
                    username,
                    backfill_days=settings.x_initial_backfill_days,
                    backfill_max_posts=settings.x_initial_backfill_max_posts,
                )
                await session.commit()
            except (ValueError, XProviderError) as exc:
                await session.rollback()
                await interaction.followup.send(f"Could not track `{username}`: {exc}")
                return
        await interaction.followup.send(
            f"Tracking @{account.account.username} ({account.account.display_name}) from now on.\n"
            f"Posts imported: {account.posts_imported:,}\n"
            f"Metric snapshots: {account.metric_snapshots_written:,}"
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
        embed.add_field(
            name="Followers",
            value=compact_number(summary.followers_count),
            inline=True,
        )
        embed.add_field(name="Posts", value=compact_number(summary.post_count), inline=True)
        embed.add_field(
            name="Tracked posts",
            value=compact_number(summary.tracked_posts),
            inline=True,
        )
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
            await interaction.followup.send(
                f"{result.reason}\n"
                f"Historical coverage: "
                f"{coverage_label(result.coverage_seconds, result.requested_seconds)}"
            )
            return
        embed = discord.Embed(title=f"@{account.username} analytics: {period}", color=0x1DA1F2)
        embed.add_field(name="Views gained", value=compact_number(result.views_gained), inline=True)
        embed.add_field(
            name="Follower growth",
            value=signed_compact_number(result.followers_gained),
            inline=True,
        )
        embed.add_field(name="Posts published", value=str(result.posts_published), inline=True)
        embed.add_field(name="Likes gained", value=compact_number(result.likes_gained), inline=True)
        embed.add_field(
            name="Reposts gained",
            value=compact_number(result.reposts_gained),
            inline=True,
        )
        embed.add_field(
            name="Replies gained",
            value=compact_number(result.replies_gained),
            inline=True,
        )
        embed.add_field(
            name="Quotes gained",
            value=compact_number(result.quotes_gained),
            inline=True,
        )
        embed.add_field(
            name="Bookmarks gained",
            value=compact_number(result.bookmarks_gained),
            inline=True,
        )
        embed.add_field(
            name="Posts published current views",
            value=compact_number(result.current_period_post_impressions),
            inline=True,
        )
        embed.add_field(
            name="Average views/post",
            value=compact_number(result.average_impressions_per_period_post),
            inline=True,
        )
        embed.add_field(
            name="Historical coverage",
            value=coverage_label(result.coverage_seconds, result.requested_seconds),
            inline=True,
        )
        if result.top_posts_by_impressions:
            top_lines = [
                f"[{safe_preview(post.text_preview, limit=60)}]({post.url}) - "
                f"{compact_number(post.impressions)} views"
                for post in result.top_posts_by_impressions
            ]
            embed.add_field(name="Top posts", value="\n".join(top_lines), inline=False)
        await interaction.followup.send(embed=embed)

    @bot.tree.command(
        name="status",
        description="Show bot, database, scheduler, and provider status.",
    )
    async def status(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        async with session_factory() as session:
            db_ok = await AccountRepository(session).ping()
            tracked_count = len(await AccountRepository(session).list_active())
        provider_ok = await provider.health_check()
        embed = discord.Embed(title="Bot status", color=discord.Color.green())
        embed.add_field(name="Discord", value="Connected", inline=True)
        embed.add_field(name="Database", value="OK" if db_ok else "Unavailable", inline=True)
        embed.add_field(name="Scheduler", value=scheduler.status_label, inline=True)
        embed.add_field(
            name="X provider",
            value="OK" if provider_ok else "Unavailable",
            inline=True,
        )
        embed.add_field(name="Provider mode", value=_provider_mode_label(settings), inline=True)
        embed.add_field(name="Tracked accounts", value=str(tracked_count), inline=True)
        if scheduler.last_result is not None:
            embed.add_field(
                name="Last collection",
                value=(
                    f"{scheduler.last_result.successes} succeeded / "
                    f"{scheduler.last_result.failures} failed"
                ),
                inline=True,
            )
        if provider.last_rate_limit is not None:
            embed.add_field(
                name="X rate limit",
                value=(
                    f"{provider.last_rate_limit.remaining or 'unknown'} remaining"
                ),
                inline=True,
            )
        scraper_stats = getattr(provider, "last_scrape_stats", None)
        if isinstance(scraper_stats, dict):
            embed.add_field(
                name="Scraper stats",
                value=(
                    f"{scraper_stats.get('posts_extracted', 0)} posts, "
                    f"{scraper_stats.get('missing_metrics', 0)} missing metrics"
                ),
                inline=True,
            )
        await interaction.followup.send(embed=embed)

    @bot.tree.command(name="refresh", description="Refresh one tracked X/Twitter account now.")
    @app_commands.describe(username="Tracked X username, with or without @")
    async def refresh(interaction: discord.Interaction, username: str) -> None:
        await interaction.response.defer(ephemeral=True)
        if not can_manage_tracking(interaction, settings):
            await interaction.followup.send("You are not allowed to refresh tracked accounts.")
            return
        async with session_factory() as session:
            account = await AccountRepository(session).get_by_username(username)
            if account is None:
                await interaction.followup.send(f"`{username}` is not being tracked.")
                return
            try:
                await CollectionService(
                    session=session,
                    provider=provider,
                    recent_posts_limit=settings.x_recent_posts_limit,
                    snapshot_min_interval_minutes=settings.snapshot_min_interval_minutes,
                ).collect_account(account, captured_at=datetime.now(UTC))
                await session.commit()
            except Exception as exc:
                await session.rollback()
                await interaction.followup.send(f"Refresh failed for `{username}`: {exc}")
                return
        await interaction.followup.send(f"Refreshed `{username}`.")

    @bot.tree.command(name="collectnow", description="Run one collection cycle now.")
    async def collectnow(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        if not can_manage_tracking(interaction, settings):
            await interaction.followup.send("You are not allowed to run collection.")
            return
        result = await scheduler.run_once()
        await interaction.followup.send(
            f"Collection finished: {result.successes} succeeded / {result.failures} failed."
        )
