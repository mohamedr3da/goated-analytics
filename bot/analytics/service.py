from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.analytics.periods import AnalyticsPeriod
from bot.database.models import AccountSnapshot, Post, PostMetricSnapshot, TrackedAccount


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
    posts_published: int


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
        }
        saw_post_metric = False
        for post in posts:
            latest = await self._post_snapshot_at_or_before(post.id, period.end)
            if latest is None:
                continue

            baseline_value_by_metric: dict[str, int] = {}
            if post.created_at >= period.start:
                baseline_value_by_metric = {
                    "views": 0,
                    "likes": 0,
                    "reposts": 0,
                    "replies": 0,
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
                }

            latest_value_by_metric = {
                "views": latest.impression_count,
                "likes": latest.like_count,
                "reposts": latest.repost_count,
                "replies": latest.reply_count,
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
            posts_published=posts_published,
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
