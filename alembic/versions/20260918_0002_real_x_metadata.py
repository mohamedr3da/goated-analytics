"""real x metadata

Revision ID: 20260918_0002
Revises: 20260918_0001
Create Date: 2026-09-18
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260918_0002"
down_revision = "20260918_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tracked_accounts", sa.Column("profile_image_url", sa.String(500)))
    op.add_column("tracked_accounts", sa.Column("account_created_at", sa.DateTime(timezone=True)))
    op.add_column("tracked_accounts", sa.Column("verified_type", sa.String(50)))
    op.add_column(
        "tracked_accounts",
        sa.Column("last_successful_refresh_at", sa.DateTime(timezone=True)),
    )
    op.add_column("tracked_accounts", sa.Column("last_refresh_error", sa.String(1000)))

    op.add_column(
        "posts",
        sa.Column("post_type", sa.String(32), nullable=False, server_default="post"),
    )
    op.add_column("posts", sa.Column("referenced_post_id", sa.String(32)))
    op.add_column("posts", sa.Column("conversation_id", sa.String(32)))
    op.add_column("posts", sa.Column("lang", sa.String(16)))
    op.add_column("posts", sa.Column("possibly_sensitive", sa.Boolean()))

    op.create_table(
        "collection_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("successes", sa.Integer(), nullable=False),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("error", sa.String(1000)),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collection_runs")),
    )
    op.create_index("ix_collection_runs_started", "collection_runs", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_collection_runs_started", table_name="collection_runs")
    op.drop_table("collection_runs")
    op.drop_column("posts", "possibly_sensitive")
    op.drop_column("posts", "lang")
    op.drop_column("posts", "conversation_id")
    op.drop_column("posts", "referenced_post_id")
    op.drop_column("posts", "post_type")
    op.drop_column("tracked_accounts", "last_refresh_error")
    op.drop_column("tracked_accounts", "last_successful_refresh_at")
    op.drop_column("tracked_accounts", "verified_type")
    op.drop_column("tracked_accounts", "account_created_at")
    op.drop_column("tracked_accounts", "profile_image_url")
