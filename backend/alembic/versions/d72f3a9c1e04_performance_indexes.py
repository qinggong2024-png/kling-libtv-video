"""performance indexes

Revision ID: d72f3a9c1e04
Revises: 8b91c2d45a10
Create Date: 2026-07-28 00:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d72f3a9c1e04"
down_revision: str | None = "8b91c2d45a10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_parent_task_user_created",
        "parent_task",
        ["user_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_parent_task_user_updated",
        "parent_task",
        ["user_id", "updated_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_generation_attempt_variant_created",
        "generation_attempt",
        ["variant_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_generation_command_status_created",
        "generation_command",
        ["status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_generation_command_status_created",
        table_name="generation_command",
    )
    op.drop_index(
        "ix_generation_attempt_variant_created",
        table_name="generation_attempt",
    )
    op.drop_index("ix_parent_task_user_updated", table_name="parent_task")
    op.drop_index("ix_parent_task_user_created", table_name="parent_task")
