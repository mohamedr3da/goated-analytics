from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import AccountSnapshot, Post, PostMetricSnapshot
from bot.providers.types import XAccount, XPost, XPostMetrics
from bot.repositories.accounts import AccountRepository
from bot.repositories.posts import PostRepository


def make_account(username: str = "first") -> XAccount:
    return XAccount(
        id="12345",
        username=username,
        display_name=f"{username} display",
        protected=False,
        verified=False,
        followers_count=100,
        following_count=10,
        post_count=50,
        listed_count=2,
        profile_image_url="https://example.com/profile.jpg",
        created_at=datetime(2020, 1, 1, tzinfo=UTC),
        verified_type="blue",
        raw={"id": "12345"},
    )


def make_post(impressions: int | None = 100) -> XPost:
    return XPost(
        id="999",
        author_id="12345",
        created_at=datetime(2026, 9, 18, 8, 0, tzinfo=UTC),
        text="A useful launch post",
        url="https://x.com/first/status/999",
        metrics=XPostMetrics(
            impression_count=impressions,
            like_count=7,
            reply_count=1,
            repost_count=2,
            quote_count=1,
            bookmark_count=3,
            video_view_count=None,
            raw={"impression_count": impressions},
        ),
        post_type="quote",
        referenced_post_id="888",
        conversation_id="777",
        lang="en",
        possibly_sensitive=False,
        raw={"id": "999"},
    )


async def test_tracked_account_keeps_identity_when_username_changes(
    session: AsyncSession,
) -> None:
    repo = AccountRepository(session)

    original = await repo.upsert_tracked_account(make_account("first"))
    renamed = await repo.upsert_tracked_account(make_account("second"))
    await session.commit()

    assert renamed.id == original.id
    assert renamed.x_user_id == "12345"
    assert renamed.username == "second"
    assert renamed.profile_image_url == "https://example.com/profile.jpg"
    assert renamed.account_created_at == datetime(2020, 1, 1, tzinfo=UTC)
    assert renamed.verified_type == "blue"
    active_accounts = await repo.list_active()
    assert [account.username for account in active_accounts] == ["second"]


async def test_account_snapshots_are_idempotent_for_account_and_timestamp(
    session: AsyncSession,
) -> None:
    repo = AccountRepository(session)
    account = await repo.upsert_tracked_account(make_account())
    captured_at = datetime(2026, 9, 18, 8, 30, tzinfo=UTC)

    first = await repo.record_account_snapshot(account, make_account(), captured_at)
    second = await repo.record_account_snapshot(account, make_account(), captured_at)
    await session.commit()

    count = await session.scalar(select(func.count(AccountSnapshot.id)))
    assert first.id == second.id
    assert count == 1


async def test_posts_and_metric_snapshots_are_idempotent(
    session: AsyncSession,
) -> None:
    account_repo = AccountRepository(session)
    post_repo = PostRepository(session)
    account = await account_repo.upsert_tracked_account(make_account())
    captured_at = datetime(2026, 9, 18, 8, 45, tzinfo=UTC)

    first_post = await post_repo.upsert_post(account, make_post(100))
    second_post = await post_repo.upsert_post(account, make_post(125))
    first_snapshot = await post_repo.record_metric_snapshot(
        first_post, make_post(100).metrics, captured_at
    )
    second_snapshot = await post_repo.record_metric_snapshot(
        second_post, make_post(125).metrics, captured_at
    )
    await session.commit()

    post_count = await session.scalar(select(func.count(Post.id)))
    snapshot_count = await session.scalar(select(func.count(PostMetricSnapshot.id)))
    assert first_post.id == second_post.id
    assert first_snapshot.id == second_snapshot.id
    assert post_count == 1
    assert snapshot_count == 1


async def test_post_metadata_is_persisted_without_duplicate_static_rows(
    session: AsyncSession,
) -> None:
    account_repo = AccountRepository(session)
    post_repo = PostRepository(session)
    account = await account_repo.upsert_tracked_account(make_account())

    post = await post_repo.upsert_post(account, make_post(100))
    await session.commit()
    persisted = await session.scalar(select(Post).where(Post.id == post.id))

    assert persisted is not None
    assert persisted.post_type == "quote"
    assert persisted.referenced_post_id == "888"
    assert persisted.conversation_id == "777"
    assert persisted.lang == "en"
    assert persisted.possibly_sensitive is False


async def test_unchanged_metric_snapshots_can_be_skipped_until_min_interval(
    session: AsyncSession,
) -> None:
    account_repo = AccountRepository(session)
    post_repo = PostRepository(session)
    account = await account_repo.upsert_tracked_account(make_account())
    post = await post_repo.upsert_post(account, make_post(100))
    first_at = datetime(2026, 9, 18, 8, 0, tzinfo=UTC)

    first = await post_repo.record_metric_snapshot(
        post,
        make_post(100).metrics,
        first_at,
        min_interval_minutes=60,
    )
    second = await post_repo.record_metric_snapshot(
        post,
        make_post(100).metrics,
        first_at + timedelta(minutes=30),
        min_interval_minutes=60,
    )
    third = await post_repo.record_metric_snapshot(
        post,
        make_post(100).metrics,
        first_at + timedelta(minutes=61),
        min_interval_minutes=60,
    )
    await session.commit()

    count = await session.scalar(select(func.count(PostMetricSnapshot.id)))
    assert first.id == second.id
    assert third.id != first.id
    assert count == 2
