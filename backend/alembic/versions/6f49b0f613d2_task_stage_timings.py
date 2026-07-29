"""add task stage timing metrics

Revision ID: 6f49b0f613d2
Revises: b8f0e9d7c4a1
Create Date: 2026-07-29 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6f49b0f613d2"
down_revision: str | None = "b8f0e9d7c4a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "parent_task",
        sa.Column("source_upload_duration_seconds", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "parent_task",
        sa.Column("analysis_duration_seconds", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "parent_task",
        sa.Column(
            "prompt_analysis_duration_seconds", sa.Float(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "parent_task",
        sa.Column("analysis_attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("parent_task", "analysis_attempt_count")
    op.drop_column("parent_task", "prompt_analysis_duration_seconds")
    op.drop_column("parent_task", "analysis_duration_seconds")
    op.drop_column("parent_task", "source_upload_duration_seconds")
