"""add durable analysis run leases and progress

Revision ID: b8f0e9d7c4a1
Revises: c47d21b8a930
Create Date: 2026-07-28 17:35:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8f0e9d7c4a1"
down_revision: str | None = "c47d21b8a930"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("parent_task", sa.Column("analysis_run_id", sa.Uuid(), nullable=True))
    op.add_column("parent_task", sa.Column("analysis_stage", sa.String(length=40), nullable=True))
    op.add_column(
        "parent_task",
        sa.Column("analysis_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "parent_task",
        sa.Column("analysis_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_parent_task_analysis_run_id", "parent_task", ["analysis_run_id"], unique=False
    )
    op.create_index(
        "ix_parent_task_analysis_stage", "parent_task", ["analysis_stage"], unique=False
    )
    op.create_index(
        "ix_parent_task_analysis_heartbeat_at",
        "parent_task",
        ["analysis_heartbeat_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_parent_task_analysis_heartbeat_at", table_name="parent_task")
    op.drop_index("ix_parent_task_analysis_stage", table_name="parent_task")
    op.drop_index("ix_parent_task_analysis_run_id", table_name="parent_task")
    op.drop_column("parent_task", "analysis_heartbeat_at")
    op.drop_column("parent_task", "analysis_started_at")
    op.drop_column("parent_task", "analysis_stage")
    op.drop_column("parent_task", "analysis_run_id")
