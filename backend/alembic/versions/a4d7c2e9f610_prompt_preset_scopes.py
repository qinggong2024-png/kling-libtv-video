"""Separate prompt presets by workflow scope.

Revision ID: a4d7c2e9f610
Revises: 3a7c9e1f5b20
Create Date: 2026-07-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a4d7c2e9f610"
down_revision: str | Sequence[str] | None = "3a7c9e1f5b20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("prompt_preset") as batch_op:
        batch_op.add_column(
            sa.Column("scope", sa.String(length=32), server_default="video", nullable=False)
        )
        batch_op.drop_constraint("uq_prompt_preset_user_name", type_="unique")
        batch_op.drop_index("ix_prompt_preset_user_order")
        batch_op.create_unique_constraint(
            "uq_prompt_preset_user_scope_name", ["user_id", "scope", "name"]
        )
        batch_op.create_index(
            "ix_prompt_preset_user_scope_order",
            ["user_id", "scope", "sort_order", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("prompt_preset") as batch_op:
        batch_op.drop_constraint("uq_prompt_preset_user_scope_name", type_="unique")
        batch_op.drop_index("ix_prompt_preset_user_scope_order")
        batch_op.create_unique_constraint("uq_prompt_preset_user_name", ["user_id", "name"])
        batch_op.create_index(
            "ix_prompt_preset_user_order",
            ["user_id", "sort_order", "created_at"],
            unique=False,
        )
        batch_op.drop_column("scope")
