from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import AccountSnapshot, PostMetricSnapshot
from bot.providers.base import XProviderError
from bot.providers.types import XAccount, XPost, XPostMetrics
from bot.repositories.accounts import AccountRepository
from bot.tasks.collector import CollectionService


class PartiallyFailingProvider:
    async def get_account_by_username(self, username: str) -> XAccount:
        if username == "bad":
            raise XProviderError("simulated upstream failure")
        return XAccount(
            id="good-id",
            username="good",
            display_name="Good Account",
            protected=False,
            verified=False,
            followers_count=200,
            following_count=20,
            post_count=10,
            listed_count=3,
            raw={},
        )

    async def get_recent_posts(
        self,
        x_user_id: str,
        *,
        max_results: int,
        since_id: str | None = None,
    ) -> list[XPost]:
        return [
            XPost(
                id="post-1",
                author_id=x_user_id,
                created_at=datetime(2026, 9, 18, 7, 0, tzinfo=UTC),
                text="Collected post",
                url="https://x.com/good/status/post-1",
                metrics=XPostMetrics(
                    impression_count=111,
                    like_count=5,
                    reply_count=1,
                    repost_count=2,
                    quote_count=0,
                    bookmark_count=1,
                    video_view_count=None,
                    raw={},
                ),
                raw={},
            )
        ]

    async def health_check(self) -> bool:
        return True


async def test_collection_failure_for_one_account_does_not_stop_other_accounts(
    session: AsyncSession,
) -> None:
    repo = AccountRepository(session)
    await repo.upsert_tracked_account(
        XAccount(
            id="good-id",
            username="good",
            display_name="Good Account",
            protected=False,
            verified=False,
            followers_count=100,
            following_count=10,
            post_count=1,
            listed_count=0,
            raw={},
        )
    )
    await repo.upsert_tracked_account(
        XAccount(
            id="bad-id",
            username="bad",
            display_name="Bad Account",
            protected=False,
            verified=False,
            followers_count=100,
            following_count=10,
            post_count=1,
            listed_count=0,
            raw={},
        )
    )
    await session.commit()

    result = await CollectionService(
        session=session,
        provider=PartiallyFailingProvider(),
        recent_posts_limit=10,
    ).collect_all(captured_at=datetime(2026, 9, 18, 9, 0, tzinfo=UTC))

    account_snapshot_count = await session.scalar(select(func.count(AccountSnapshot.id)))
    post_metric_count = await session.scalar(select(func.count(PostMetricSnapshot.id)))
    assert result.successes == 1
    assert result.failures == 1
    assert account_snapshot_count == 1
    assert post_metric_count == 1

