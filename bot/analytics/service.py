from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.analytics.periods import AnalyticsPeriod
from bot.database.models import AccountSnapshot, Post, PostMetricSnapshot, TrackedAccount
from bot.utils.time import ensure_utc


@dataclass(frozen=True)
class TopPost:
    x_post_id: str
    text_preview: str
    url: str
    created_at: object
    impressions: int | None
    likes: int | None
    replies: int | None
    reposts: int | None
    quotes: int | None
    bookmarks: int | None


@dataclass(frozen=True)
class PeriodAnalytics:
    available: bool
    reason: str
    period: AnalyticsPeriod
    followers_gained: int | None
    views_gained: int | None
    likes_gained: int | None
    reposts_gained: int | None
    replies_gained: int | None
    quotes_gained: int | None
    bookmarks_gained: int | None
    posts_published: int
    requested_seconds: int
    coverage_seconds: int
    current_period_post_impressions: int | None
    current_period_post_likes: int | None
    average_impressions_per_period_post: int | None
    top_posts_by_impressions: list[TopPost]


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def summarize_account(
        self,
        account: TrackedAccount,
        period: AnalyticsPeriod,
    ) -> PeriodAnalytics:
        reasons: list[str] = []
        start_account = await self._account_snapshot_at_or_before(account.id, period.start)
        end_account = await self._account_snapshot_at_or_before(account.id, period.end)
        first_account = await self._first_account_snapshot(account.id)
        coverage_start = period.start
        if first_account is not None and ensure_utc(first_account.captured_at) > period.start:
            coverage_start = ensure_utc(first_account.captured_at)
        coverage_seconds = max(0, int((period.end - coverage_start).total_seconds()))
        requested_seconds = int((period.end - period.start).total_seconds())

        if coverage_seconds < requested_seconds:
            reasons.append(
                "Only "
                f"{coverage_seconds // 3600}h of tracking history is available for this period."
            )

        followers_gained: int | None = None
        if start_account is None or end_account is None:
            reasons.append("Missing account snapshot baseline for the requested period.")
        elif start_account.followers_count is None or end_account.followers_count is None:
            reasons.append("Missing follower metric values for the requested period.")
        else:
            followers_gained = end_account.followers_count - start_account.followers_count

        posts = await self._posts_visible_by(account.id, period.end)
        metric_totals = {
            "views": 0,
            "likes": 0,
            "reposts": 0,
            "replies": 0,
            "quotes": 0,
            "bookmarks": 0,
        }
        saw_post_metric = False
        for post in posts:
            latest = await self._post_snapshot_at_or_before(post.id, period.end)
            if latest is None:
                continue

            baseline_value_by_metric: dict[str, int] = {}
            if ensure_utc(post.created_at) >= period.start:
                baseline_value_by_metric = {
                    "views": 0,
                    "likes": 0,
                    "reposts": 0,
                    "replies": 0,
                    "quotes": 0,
                    "bookmarks": 0,
                }
            else:
                baseline = await self._post_snapshot_at_or_before(post.id, period.start)
                if baseline is None:
                    reasons.append(
                        "Missing post metric baseline for "
                        f"@{account.username} post {post.x_post_id}."
                    )
                    continue
                baseline_value_by_metric = {
                    "views": baseline.impression_count,
                    "likes": baseline.like_count,
                    "reposts": baseline.repost_count,
                    "replies": baseline.reply_count,
                    "quotes": baseline.quote_count,
                    "bookmarks": baseline.bookmark_count,
                }

            latest_value_by_metric = {
                "views": latest.impression_count,
                "likes": latest.like_count,
                "reposts": latest.repost_count,
                "replies": latest.reply_count,
                "quotes": latest.quote_count,
                "bookmarks": latest.bookmark_count,
            }

            if any(value is None for value in latest_value_by_metric.values()):
                reasons.append(
                    "Missing current post metric values for "
                    f"@{account.username} post {post.x_post_id}."
                )
                continue
            if any(value is None for value in baseline_value_by_metric.values()):
                reasons.append(
                    "Missing baseline post metric values for "
                    f"@{account.username} post {post.x_post_id}."
                )
                continue

            saw_post_metric = True
            for key, latest_value in latest_value_by_metric.items():
                baseline_value = baseline_value_by_metric[key]
                metric_totals[key] += latest_value - baseline_value

        posts_published = await self._posts_published_count(account.id, period)
        period_post_performance = await self._current_period_post_performance(account.id, period)

        if not posts:
            saw_post_metric = True
        if not saw_post_metric:
            reasons.append("Missing usable post metric snapshots for the requested period.")

        available = not reasons
        return PeriodAnalytics(
            available=available,
            reason="Available." if available else " ".join(dict.fromkeys(reasons)),
            period=period,
            followers_gained=followers_gained,
            views_gained=metric_totals["views"] if available else None,
            likes_gained=metric_totals["likes"] if available else None,
            reposts_gained=metric_totals["reposts"] if available else None,
            replies_gained=metric_totals["replies"] if available else None,
            quotes_gained=metric_totals["quotes"] if available else None,
            bookmarks_gained=metric_totals["bookmarks"] if available else None,
            posts_published=posts_published,
            requested_seconds=requested_seconds,
            coverage_seconds=coverage_seconds,
            current_period_post_impressions=period_post_performance["impressions"],
            current_period_post_likes=period_post_performance["likes"],
            average_impressions_per_period_post=(
                period_post_performance["impressions"] // posts_published
                if posts_published and period_post_performance["impressions"] is not None
                else None
            ),
            top_posts_by_impressions=period_post_performance["top_posts"],
        )

    async def _account_snapshot_at_or_before(
        self,
        account_id: int,
        captured_at,
    ) -> AccountSnapshot | None:
        statement = (
            select(AccountSnapshot)
            .where(
                AccountSnapshot.account_id == account_id,
                AccountSnapshot.captured_at <= captured_at,
            )
            .order_by(AccountSnapshot.captured_at.desc(), AccountSnapshot.id.desc())
            .limit(1)
        )
        return await self.session.scalar(statement)

    async def _first_account_snapshot(self, account_id: int) -> AccountSnapshot | None:
        statement = (
            select(AccountSnapshot)
            .where(AccountSnapshot.account_id == account_id)
            .order_by(AccountSnapshot.captured_at.asc(), AccountSnapshot.id.asc())
            .limit(1)
        )
        return await self.session.scalar(statement)

    async def _post_snapshot_at_or_before(
        self,
        post_id: int,
        captured_at,
    ) -> PostMetricSnapshot | None:
        statement = (
            select(PostMetricSnapshot)
            .where(
                PostMetricSnapshot.post_id == post_id,
                PostMetricSnapshot.captured_at <= captured_at,
            )
            .order_by(PostMetricSnapshot.captured_at.desc(), PostMetricSnapshot.id.desc())
            .limit(1)
        )
        return await self.session.scalar(statement)

    async def _posts_visible_by(self, account_id: int, end_at) -> list[Post]:
        statement: Select[tuple[Post]] = (
            select(Post).where(Post.account_id == account_id, Post.created_at <= end_at)
        )
        return list((await self.session.scalars(statement)).all())

    async def _posts_published_count(self, account_id: int, period: AnalyticsPeriod) -> int:
        statement = select(func.count(Post.id)).where(
            Post.account_id == account_id,
            Post.created_at >= period.start,
            Post.created_at <= period.end,
        )
        return int(await self.session.scalar(statement) or 0)

    async def _current_period_post_performance(
        self,
        account_id: int,
        period: AnalyticsPeriod,
    ) -> dict:
        statement: Select[tuple[Post]] = (
            select(Post)
            .where(
                Post.account_id == account_id,
                Post.created_at >= period.start,
                Post.created_at <= period.end,
            )
            .order_by(Post.created_at.desc())
        )
        posts = list((await self.session.scalars(statement)).all())
        impressions_total: int | None = 0
        likes_total: int | None = 0
        top_posts: list[TopPost] = []
        for post in posts:
            latest = await self._post_snapshot_at_or_before(post.id, period.end)
            if latest is None:
                continue
            if latest.impression_count is None:
                impressions_total = None
            elif impressions_total is not None:
                impressions_total += latest.impression_count
            if latest.like_count is None:
                likes_total = None
            elif likes_total is not None:
                likes_total += latest.like_count
            top_posts.append(
                TopPost(
                    x_post_id=post.x_post_id,
                    text_preview=post.text_preview,
                    url=post.url,
                    created_at=ensure_utc(post.created_at),
                    impressions=latest.impression_count,
                    likes=latest.like_count,
                    replies=latest.reply_count,
                    reposts=latest.repost_count,
                    quotes=latest.quote_count,
                    bookmarks=latest.bookmark_count,
                )
            )
        top_posts.sort(key=lambda item: item.impressions or -1, reverse=True)
        return {
            "impressions": impressions_total,
            "likes": likes_total,
            "top_posts": top_posts[:3],
        }
