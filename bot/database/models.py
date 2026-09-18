from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.database.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class TrackedAccount(Base):
    __tablename__ = "tracked_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    x_user_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(15), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    profile_image_url: Mapped[str | None] = mapped_column(String(500))
    account_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_type: Mapped[str | None] = mapped_column(String(50))
    tracking_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
    is_tracking_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    protected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_successful_refresh_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_refresh_error: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )

    snapshots: Mapped[list[AccountSnapshot]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
    )
    posts: Mapped[list[Post]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
    )


class AccountSnapshot(Base):
    __tablename__ = "account_snapshots"
    __table_args__ = (
        UniqueConstraint("account_id", "captured_at", name="uq_account_snapshot_time"),
        Index("ix_account_snapshots_account_captured", "account_id", "captured_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("tracked_accounts.id"), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    followers_count: Mapped[int | None] = mapped_column(Integer)
    following_count: Mapped[int | None] = mapped_column(Integer)
    post_count: Mapped[int | None] = mapped_column(Integer)
    listed_count: Mapped[int | None] = mapped_column(Integer)
    raw_metrics: Mapped[dict | None] = mapped_column(JSON)

    account: Mapped[TrackedAccount] = relationship(back_populates="snapshots")


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (
        Index("ix_posts_account_created", "account_id", "created_at"),
        Index("ix_posts_account_first_seen", "account_id", "first_seen_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    x_post_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("tracked_accounts.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    text_preview: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str] = mapped_column(String(255), nullable=False)
    post_type: Mapped[str] = mapped_column(String(32), default="post", nullable=False)
    referenced_post_id: Mapped[str | None] = mapped_column(String(32))
    conversation_id: Mapped[str | None] = mapped_column(String(32))
    lang: Mapped[str | None] = mapped_column(String(16))
    possibly_sensitive: Mapped[bool | None] = mapped_column(Boolean)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
    raw_data: Mapped[dict | None] = mapped_column(JSON)

    account: Mapped[TrackedAccount] = relationship(back_populates="posts")
    metric_snapshots: Mapped[list[PostMetricSnapshot]] = relationship(
        back_populates="post",
        cascade="all, delete-orphan",
    )


class PostMetricSnapshot(Base):
    __tablename__ = "post_metric_snapshots"
    __table_args__ = (
        UniqueConstraint("post_id", "captured_at", name="uq_post_metric_snapshot_time"),
        Index("ix_post_metric_snapshots_post_captured", "post_id", "captured_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    impression_count: Mapped[int | None] = mapped_column(Integer)
    like_count: Mapped[int | None] = mapped_column(Integer)
    reply_count: Mapped[int | None] = mapped_column(Integer)
    repost_count: Mapped[int | None] = mapped_column(Integer)
    quote_count: Mapped[int | None] = mapped_column(Integer)
    bookmark_count: Mapped[int | None] = mapped_column(Integer)
    video_view_count: Mapped[int | None] = mapped_column(Integer)
    raw_metrics: Mapped[dict | None] = mapped_column(JSON)

    post: Mapped[Post] = relationship(back_populates="metric_snapshots")


class CollectionRun(Base):
    __tablename__ = "collection_runs"
    __table_args__ = (
        Index("ix_collection_runs_started", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    successes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error: Mapped[str | None] = mapped_column(String(1000))
