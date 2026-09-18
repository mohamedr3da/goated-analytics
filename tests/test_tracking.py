from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import AccountSnapshot, Post, PostMetricSnapshot
from bot.providers.types import XAccount, XPost, XPostMetrics
from bot.services.tracking import TrackingService


class BackfillProvider:
    last_rate_limit = None

    async def get_account_by_username(self, username: str) -> XAccount:
        return XAccount(
            id="acct-1",
            username=username,
            display_name="Backfill Account",
            protected=False,
            verified=True,
            followers_count=1000,
            following_count=100,
            post_count=50,
            listed_count=5,
            raw={},
        )

    async def get_recent_posts(
        self,
        x_user_id: str,
        *,
        max_results: int,
        since_id: str | None = None,
    ) -> list[XPost]:
        return []

    async def get_posts_window(
        self,
        x_user_id: str,
        *,
        start_time: datetime,
        end_time: datetime,
        max_posts: int,
    ) -> list[XPost]:
        return [
            XPost(
                id="post-1",
                author_id=x_user_id,
                created_at=end_time - timedelta(days=1),
                text="first real post",
                url="https://x.com/example/status/post-1",
                metrics=XPostMetrics(
                    impression_count=100,
                    like_count=10,
                    reply_count=1,
                    repost_count=2,
                    quote_count=3,
                    bookmark_count=4,
                    video_view_count=50,
                    raw={},
                ),
                raw={},
            ),
            XPost(
                id="post-2",
                author_id=x_user_id,
                created_at=end_time - timedelta(days=2),
                text="second real post",
                url="https://x.com/example/status/post-2",
                metrics=XPostMetrics(
                    impression_count=200,
                    like_count=20,
                    reply_count=2,
                    repost_count=4,
                    quote_count=6,
                    bookmark_count=8,
                    video_view_count=None,
                    raw={},
                ),
                raw={},
            ),
        ]

    async def health_check(self) -> bool:
        return True


async def test_track_performs_initial_backfill_and_reports_import_counts(
    session: AsyncSession,
) -> None:
    service = TrackingService(session, BackfillProvider())
    captured_at = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)

    result = await service.track(
        "creator",
        captured_at=captured_at,
        backfill_days=30,
        backfill_max_posts=200,
    )
    await session.commit()

    account_snapshot_count = await session.scalar(select(func.count(AccountSnapshot.id)))
    post_count = await session.scalar(select(func.count(Post.id)))
    post_snapshot_count = await session.scalar(select(func.count(PostMetricSnapshot.id)))
    assert result.account.username == "creator"
    assert result.posts_imported == 2
    assert result.metric_snapshots_written == 2
    assert account_snapshot_count == 1
    assert post_count == 2
    assert post_snapshot_count == 2

