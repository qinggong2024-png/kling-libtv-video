"""Persist reusable Kling subject element creation jobs.

Revision ID: e8c1a4b7d930
Revises: d9e2f3a4b5c6
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e8c1a4b7d930"
down_revision: str | Sequence[str] | None = "d9e2f3a4b5c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "subject_element_job",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("parent_task_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("external_task_id", sa.String(length=160), nullable=False),
        sa.Column("provider_task_id", sa.String(length=160), nullable=True),
        sa.Column("element_id", sa.String(length=160), nullable=True),
        sa.Column("name", sa.String(length=20), nullable=False),
        sa.Column("description", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=80), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["parent_task_id"],
            ["parent_task.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_task_id", name="uq_subject_element_job_external"),
        sa.UniqueConstraint("parent_task_id", name="uq_subject_element_job_task"),
    )
    op.create_index(
        "ix_subject_element_job_parent_task_id",
        "subject_element_job",
        ["parent_task_id"],
    )
    op.create_index(
        "ix_subject_element_job_user_id",
        "subject_element_job",
        ["user_id"],
    )
    op.create_index(
        "ix_subject_element_job_provider_task_id",
        "subject_element_job",
        ["provider_task_id"],
    )
    op.create_index(
        "ix_subject_element_job_element_id",
        "subject_element_job",
        ["element_id"],
    )
    op.create_index(
        "ix_subject_element_job_status",
        "subject_element_job",
        ["status"],
    )
    op.create_index(
        "ix_subject_element_job_recovery",
        "subject_element_job",
        ["status", "next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_subject_element_job_recovery", table_name="subject_element_job")
    op.drop_index("ix_subject_element_job_status", table_name="subject_element_job")
    op.drop_index("ix_subject_element_job_element_id", table_name="subject_element_job")
    op.drop_index("ix_subject_element_job_provider_task_id", table_name="subject_element_job")
    op.drop_index("ix_subject_element_job_user_id", table_name="subject_element_job")
    op.drop_index("ix_subject_element_job_parent_task_id", table_name="subject_element_job")
    op.drop_table("subject_element_job")
