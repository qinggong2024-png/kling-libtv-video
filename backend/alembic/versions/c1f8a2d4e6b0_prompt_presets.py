"""Add user-owned custom prompt presets.

Revision ID: c1f8a2d4e6b0
Revises: f2b6d8a13c47
Create Date: 2026-07-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c1f8a2d4e6b0"
down_revision: str | Sequence[str] | None = "f2b6d8a13c47"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prompt_preset",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name", name="uq_prompt_preset_user_name"),
    )
    op.create_index("ix_prompt_preset_user_id", "prompt_preset", ["user_id"])
    op.create_index(
        "ix_prompt_preset_user_order",
        "prompt_preset",
        ["user_id", "sort_order", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_prompt_preset_user_order", table_name="prompt_preset")
    op.drop_index("ix_prompt_preset_user_id", table_name="prompt_preset")
    op.drop_table("prompt_preset")
