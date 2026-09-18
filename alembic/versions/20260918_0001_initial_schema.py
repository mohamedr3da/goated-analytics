"""initial schema

Revision ID: 20260918_0001
Revises:
Create Date: 2026-09-18
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260918_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tracked_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("x_user_id", sa.String(length=32), nullable=False),
        sa.Column("username", sa.String(length=15), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("tracking_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_tracking_enabled", sa.Boolean(), nullable=False),
        sa.Column("protected", sa.Boolean(), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tracked_accounts")),
        sa.UniqueConstraint("x_user_id", name=op.f("uq_tracked_accounts_x_user_id")),
    )
    op.create_index(
        op.f("ix_tracked_accounts_username"),
        "tracked_accounts",
        ["username"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tracked_accounts_x_user_id"),
        "tracked_accounts",
        ["x_user_id"],
        unique=False,
    )

    op.create_table(
        "account_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("followers_count", sa.Integer(), nullable=True),
        sa.Column("following_count", sa.Integer(), nullable=True),
        sa.Column("post_count", sa.Integer(), nullable=True),
        sa.Column("listed_count", sa.Integer(), nullable=True),
        sa.Column("raw_metrics", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["tracked_accounts.id"],
            name=op.f("fk_account_snapshots_account_id_tracked_accounts"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_account_snapshots")),
        sa.UniqueConstraint("account_id", "captured_at", name="uq_account_snapshot_time"),
    )
    op.create_index(
        "ix_account_snapshots_account_captured",
        "account_snapshots",
        ["account_id", "captured_at"],
        unique=False,
    )

    op.create_table(
        "posts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("x_post_id", sa.String(length=32), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("text_preview", sa.String(length=500), nullable=False),
        sa.Column("url", sa.String(length=255), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["tracked_accounts.id"],
            name=op.f("fk_posts_account_id_tracked_accounts"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_posts")),
        sa.UniqueConstraint("x_post_id", name=op.f("uq_posts_x_post_id")),
    )
    op.create_index("ix_posts_account_created", "posts", ["account_id", "created_at"])
    op.create_index("ix_posts_account_first_seen", "posts", ["account_id", "first_seen_at"])
    op.create_index(op.f("ix_posts_x_post_id"), "posts", ["x_post_id"], unique=False)

    op.create_table(
        "post_metric_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("impression_count", sa.Integer(), nullable=True),
        sa.Column("like_count", sa.Integer(), nullable=True),
        sa.Column("reply_count", sa.Integer(), nullable=True),
        sa.Column("repost_count", sa.Integer(), nullable=True),
        sa.Column("quote_count", sa.Integer(), nullable=True),
        sa.Column("bookmark_count", sa.Integer(), nullable=True),
        sa.Column("video_view_count", sa.Integer(), nullable=True),
        sa.Column("raw_metrics", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["post_id"],
            ["posts.id"],
            name=op.f("fk_post_metric_snapshots_post_id_posts"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_post_metric_snapshots")),
        sa.UniqueConstraint("post_id", "captured_at", name="uq_post_metric_snapshot_time"),
    )
    op.create_index(
        "ix_post_metric_snapshots_post_captured",
        "post_metric_snapshots",
        ["post_id", "captured_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_post_metric_snapshots_post_captured", table_name="post_metric_snapshots")
    op.drop_table("post_metric_snapshots")
    op.drop_index(op.f("ix_posts_x_post_id"), table_name="posts")
    op.drop_index("ix_posts_account_first_seen", table_name="posts")
    op.drop_index("ix_posts_account_created", table_name="posts")
    op.drop_table("posts")
    op.drop_index("ix_account_snapshots_account_captured", table_name="account_snapshots")
    op.drop_table("account_snapshots")
    op.drop_index(op.f("ix_tracked_accounts_x_user_id"), table_name="tracked_accounts")
    op.drop_index(op.f("ix_tracked_accounts_username"), table_name="tracked_accounts")
    op.drop_table("tracked_accounts")

