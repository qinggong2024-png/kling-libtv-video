"""add private personal video learning profiles

Revision ID: 5c8f2a1d9e70
Revises: d1e7a3c5f902
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5c8f2a1d9e70"
down_revision: str | Sequence[str] | None = "d1e7a3c5f902"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "app_user",
        sa.Column(
            "video_learning_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.create_table(
        "user_video_learning_profile",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("scope_key", sa.String(length=240), nullable=False),
        sa.Column("template_id", sa.String(length=80), nullable=False),
        sa.Column("site_profile_id", sa.String(length=80), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("deterministic_guidance", sa.Text(), nullable=False, server_default=""),
        sa.Column("llm_prompt_guidance", sa.Text(), nullable=False, server_default=""),
        sa.Column("preferred_action_ids_json", sa.JSON(), nullable=False),
        sa.Column("avoided_action_ids_json", sa.JSON(), nullable=False),
        sa.Column("llm_preferred_action_ids_json", sa.JSON(), nullable=False),
        sa.Column("llm_avoided_action_ids_json", sa.JSON(), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("positive_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("negative_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("synthesized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "scope_key", name="uq_video_learning_profile_user_scope"),
    )
    op.create_index(
        "ix_user_video_learning_profile_user_id",
        "user_video_learning_profile",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_video_learning_profile_user_updated",
        "user_video_learning_profile",
        ["user_id", "updated_at"],
        unique=False,
    )
    op.create_table(
        "feedback_learning_job",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("scope_key", sa.String(length=240), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="PENDING"),
        sa.Column("profile_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "scope_key", name="uq_feedback_learning_job_user_scope"),
    )
    op.create_index(
        "ix_feedback_learning_job_user_id",
        "feedback_learning_job",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_feedback_learning_job_status_available",
        "feedback_learning_job",
        ["status", "available_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_feedback_learning_job_status_available", table_name="feedback_learning_job")
    op.drop_index("ix_feedback_learning_job_user_id", table_name="feedback_learning_job")
    op.drop_table("feedback_learning_job")
    op.drop_index(
        "ix_video_learning_profile_user_updated",
        table_name="user_video_learning_profile",
    )
    op.drop_index(
        "ix_user_video_learning_profile_user_id",
        table_name="user_video_learning_profile",
    )
    op.drop_table("user_video_learning_profile")
    op.drop_column("app_user", "video_learning_enabled")
