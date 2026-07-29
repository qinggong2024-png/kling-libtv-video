"""add generation feedback learning

Revision ID: e31a92f74c08
Revises: a16c4f2e9b77
Create Date: 2026-07-28 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e31a92f74c08"
down_revision: str | None = "a16c4f2e9b77"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

feedback_value = sa.Enum("LIKE", "DISLIKE", name="feedbackvalue", native_enum=False)
variant_kind = sa.Enum("STABLE", "DYNAMIC", name="variantkind", native_enum=False)


def upgrade() -> None:
    op.create_table(
        "generation_feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("parent_task_id", sa.Uuid(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column("variant_type", variant_kind, nullable=False),
        sa.Column("value", feedback_value, nullable=False),
        sa.Column("scene_key", sa.String(length=64), nullable=False),
        sa.Column("context_json", sa.JSON(), nullable=False),
        sa.Column("prompt_snapshot", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["parent_task_id"], ["parent_task.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["variant_id"], ["generation_variant.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("variant_id", name="uq_generation_feedback_variant"),
    )
    op.create_index(
        "ix_generation_feedback_user_id",
        "generation_feedback",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_generation_feedback_parent_task_id",
        "generation_feedback",
        ["parent_task_id"],
        unique=False,
    )
    op.create_index(
        "ix_generation_feedback_variant_id",
        "generation_feedback",
        ["variant_id"],
        unique=False,
    )
    op.create_index(
        "ix_generation_feedback_learning",
        "generation_feedback",
        ["user_id", "scene_key", "variant_type", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_generation_feedback_learning", table_name="generation_feedback")
    op.drop_index("ix_generation_feedback_variant_id", table_name="generation_feedback")
    op.drop_index("ix_generation_feedback_parent_task_id", table_name="generation_feedback")
    op.drop_index("ix_generation_feedback_user_id", table_name="generation_feedback")
    op.drop_table("generation_feedback")
