from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from bot.analytics.periods import AnalyticsPeriod
from bot.analytics.service import AnalyticsService
from bot.providers.types import XAccount, XPost, XPostMetrics
from bot.repositories.accounts import AccountRepository
from bot.repositories.posts import PostRepository


def account_payload(followers: int) -> XAccount:
    return XAccount(
        id="acct-1",
        username="creator",
        display_name="Creator",
        protected=False,
        verified=True,
        followers_count=followers,
        following_count=10,
        post_count=5,
        listed_count=1,
        raw={},
    )


def post_payload(
    post_id: str,
    created_at: datetime,
    impressions: int | None,
) -> XPost:
    return XPost(
        id=post_id,
        author_id="acct-1",
        created_at=created_at,
        text=f"post {post_id}",
        url=f"https://x.com/creator/status/{post_id}",
        metrics=XPostMetrics(
            impression_count=impressions,
            like_count=10,
            reply_count=2,
            repost_count=3,
            quote_count=1,
            bookmark_count=4,
            video_view_count=None,
            raw={},
        ),
        raw={},
    )


async def tracked_account_with_snapshots(
    session: AsyncSession,
    start: datetime,
    end: datetime,
):
    account_repo = AccountRepository(session)
    account = await account_repo.upsert_tracked_account(account_payload(100))
    await account_repo.record_account_snapshot(account, account_payload(100), start)
    await account_repo.record_account_snapshot(account, account_payload(150), end)
    return account


async def test_period_analytics_uses_snapshot_deltas_for_growth(
    session: AsyncSession,
) -> None:
    start = datetime(2026, 9, 17, 9, 0, tzinfo=UTC)
    end = datetime(2026, 9, 18, 9, 0, tzinfo=UTC)
    account = await tracked_account_with_snapshots(session, start, end)
    post_repo = PostRepository(session)
    post = await post_repo.upsert_post(
        account,
        post_payload("1", start - timedelta(days=2), 1_000),
    )
    await post_repo.record_metric_snapshot(
        post, post_payload("1", start - timedelta(days=2), 1_000).metrics, start
    )
    await post_repo.record_metric_snapshot(
        post, post_payload("1", start - timedelta(days=2), 1_450).metrics, end
    )
    await session.commit()

    result = await AnalyticsService(session).summarize_account(
        account,
        AnalyticsPeriod(start=start, end=end),
    )

    assert result.available
    assert result.followers_gained == 50
    assert result.views_gained == 450
    assert result.posts_published == 0


async def test_posts_created_inside_period_use_zero_baseline_for_period_views(
    session: AsyncSession,
) -> None:
    start = datetime(2026, 9, 17, 9, 0, tzinfo=UTC)
    end = datetime(2026, 9, 18, 9, 0, tzinfo=UTC)
    account = await tracked_account_with_snapshots(session, start, end)
    post_repo = PostRepository(session)
    created_at = start + timedelta(hours=2)
    post = await post_repo.upsert_post(account, post_payload("2", created_at, 20))
    await post_repo.record_metric_snapshot(
        post, post_payload("2", created_at, 20).metrics, start + timedelta(hours=3)
    )
    await post_repo.record_metric_snapshot(post, post_payload("2", created_at, 90).metrics, end)
    await session.commit()

    result = await AnalyticsService(session).summarize_account(
        account,
        AnalyticsPeriod(start=start, end=end),
    )

    assert result.available
    assert result.views_gained == 90
    assert result.posts_published == 1


async def test_analytics_refuses_to_fake_views_without_pre_period_baseline(
    session: AsyncSession,
) -> None:
    start = datetime(2026, 9, 17, 9, 0, tzinfo=UTC)
    end = datetime(2026, 9, 18, 9, 0, tzinfo=UTC)
    account = await tracked_account_with_snapshots(session, start, end)
    post_repo = PostRepository(session)
    post = await post_repo.upsert_post(
        account,
        post_payload("3", start - timedelta(days=10), 900),
    )
    await post_repo.record_metric_snapshot(post, post_payload("3", start, 1_000).metrics, end)
    await session.commit()

    result = await AnalyticsService(session).summarize_account(
        account,
        AnalyticsPeriod(start=start, end=end),
    )

    assert not result.available
    assert result.views_gained is None
    assert "baseline" in result.reason.lower()


async def test_missing_metric_values_do_not_crash_or_invent_values(
    session: AsyncSession,
) -> None:
    start = datetime(2026, 9, 17, 9, 0, tzinfo=UTC)
    end = datetime(2026, 9, 18, 9, 0, tzinfo=UTC)
    account = await tracked_account_with_snapshots(session, start, end)
    post_repo = PostRepository(session)
    post = await post_repo.upsert_post(
        account,
        post_payload("4", start - timedelta(days=1), None),
    )
    await post_repo.record_metric_snapshot(post, post_payload("4", start, None).metrics, start)
    await post_repo.record_metric_snapshot(post, post_payload("4", start, None).metrics, end)
    await session.commit()

    result = await AnalyticsService(session).summarize_account(
        account,
        AnalyticsPeriod(start=start, end=end),
    )

    assert not result.available
    assert result.views_gained is None
    assert "missing" in result.reason.lower()


async def test_analytics_reports_current_performance_for_posts_published_in_period(
    session: AsyncSession,
) -> None:
    start = datetime(2026, 9, 17, 9, 0, tzinfo=UTC)
    end = datetime(2026, 9, 18, 9, 0, tzinfo=UTC)
    account = await tracked_account_with_snapshots(session, start, end)
    post_repo = PostRepository(session)
    first = await post_repo.upsert_post(
        account,
        post_payload("5", start + timedelta(hours=1), 500),
    )
    second = await post_repo.upsert_post(
        account,
        post_payload("6", start + timedelta(hours=2), 250),
    )
    await post_repo.record_metric_snapshot(
        first, post_payload("5", start + timedelta(hours=1), 500).metrics, end
    )
    await post_repo.record_metric_snapshot(
        second, post_payload("6", start + timedelta(hours=2), 250).metrics, end
    )
    await session.commit()

    result = await AnalyticsService(session).summarize_account(
        account,
        AnalyticsPeriod(start=start, end=end),
    )

    assert result.current_period_post_impressions == 750
    assert result.average_impressions_per_period_post == 375
    assert [post.x_post_id for post in result.top_posts_by_impressions] == ["5", "6"]


async def test_analytics_reports_partial_coverage_without_faking_full_period(
    session: AsyncSession,
) -> None:
    start = datetime(2026, 9, 11, 9, 0, tzinfo=UTC)
    first_snapshot = datetime(2026, 9, 15, 9, 0, tzinfo=UTC)
    end = datetime(2026, 9, 18, 9, 0, tzinfo=UTC)
    account = await tracked_account_with_snapshots(session, first_snapshot, end)
    await session.commit()

    result = await AnalyticsService(session).summarize_account(
        account,
        AnalyticsPeriod(start=start, end=end),
    )

    assert not result.available
    assert result.coverage_seconds == int((end - first_snapshot).total_seconds())
    assert result.requested_seconds == int((end - start).total_seconds())
    assert "Only" in result.reason
