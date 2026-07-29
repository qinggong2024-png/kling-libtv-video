"""add provider-neutral generation metadata for Kling CLI

Revision ID: a16c4f2e9b77
Revises: d72f3a9c1e04
Create Date: 2026-07-28 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a16c4f2e9b77"
down_revision: str | None = "d72f3a9c1e04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "generation_attempt",
        sa.Column("provider", sa.String(length=80), server_default="libtv", nullable=False),
    )
    op.add_column(
        "generation_attempt", sa.Column("provider_model", sa.String(length=160), nullable=True)
    )
    op.add_column(
        "generation_attempt", sa.Column("provider_status", sa.String(length=40), nullable=True)
    )
    op.add_column(
        "generation_attempt",
        sa.Column("provider_raw_status", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "generation_attempt",
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "generation_attempt",
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "generation_attempt",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("generation_attempt", sa.Column("output_url", sa.Text(), nullable=True))
    op.add_column(
        "generation_attempt",
        sa.Column("local_output_path", sa.String(length=500), nullable=True),
    )
    op.add_column("generation_attempt", sa.Column("credits_consumed", sa.Integer(), nullable=True))
    op.add_column("generation_attempt", sa.Column("error_message", sa.Text(), nullable=True))
    op.add_column("generation_attempt", sa.Column("raw_response_json", sa.JSON(), nullable=True))
    op.create_index(
        "ix_generation_attempt_provider_task",
        "generation_attempt",
        ["provider", "task_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_generation_attempt_provider_task", table_name="generation_attempt")
    op.drop_column("generation_attempt", "raw_response_json")
    op.drop_column("generation_attempt", "error_message")
    op.drop_column("generation_attempt", "credits_consumed")
    op.drop_column("generation_attempt", "local_output_path")
    op.drop_column("generation_attempt", "output_url")
    op.drop_column("generation_attempt", "completed_at")
    op.drop_column("generation_attempt", "last_polled_at")
    op.drop_column("generation_attempt", "submitted_at")
    op.drop_column("generation_attempt", "provider_raw_status")
    op.drop_column("generation_attempt", "provider_status")
    op.drop_column("generation_attempt", "provider_model")
    op.drop_column("generation_attempt", "provider")
