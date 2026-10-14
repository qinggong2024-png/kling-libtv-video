"""Persist LibTV to Cutflow handoff packages.

Revision ID: c7d8e9f0a1b2
Revises: e5f6a7b8c901
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c7d8e9f0a1b2"
down_revision: str | Sequence[str] | None = "e5f6a7b8c901"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cutflow_handoff",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("parent_task_id", sa.Uuid(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column("artifact_id", sa.Uuid(), nullable=False),
        sa.Column("handoff_key", sa.String(length=160), nullable=False),
        sa.Column("contract_version", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("manifest_path", sa.String(length=1000), nullable=False),
        sa.Column("manifest_json", sa.JSON(), nullable=False),
        sa.Column("cutflow_batch_id", sa.String(length=160), nullable=True),
        sa.Column("cutflow_editor_url", sa.String(length=1000), nullable=True),
        sa.Column("output_path", sa.String(length=1000), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("outputs_json", sa.JSON(), nullable=False),
        sa.Column("lease_token", sa.String(length=40), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_count", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(["parent_task_id"], ["parent_task.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["variant_id"], ["generation_variant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["artifact_id"], ["download_artifact.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("handoff_key", name="uq_cutflow_handoff_key"),
        sa.UniqueConstraint("user_id", "artifact_id", name="uq_cutflow_handoff_user_artifact"),
    )
    op.create_index(
        "ix_cutflow_handoff_status",
        "cutflow_handoff",
        ["status"],
    )
    op.create_index(
        "ix_cutflow_handoff_user_id",
        "cutflow_handoff",
        ["user_id"],
    )
    op.create_index(
        "ix_cutflow_handoff_parent_task_id",
        "cutflow_handoff",
        ["parent_task_id"],
    )
    op.create_index(
        "ix_cutflow_handoff_variant_id",
        "cutflow_handoff",
        ["variant_id"],
    )
    op.create_index(
        "ix_cutflow_handoff_artifact_id",
        "cutflow_handoff",
        ["artifact_id"],
    )
    op.create_index(
        "ix_cutflow_handoff_status_updated",
        "cutflow_handoff",
        ["status", "updated_at"],
    )
    op.create_index(
        "ix_cutflow_handoff_user_created",
        "cutflow_handoff",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_cutflow_handoff_status", table_name="cutflow_handoff")
    op.drop_index("ix_cutflow_handoff_user_created", table_name="cutflow_handoff")
    op.drop_index("ix_cutflow_handoff_status_updated", table_name="cutflow_handoff")
    op.drop_index("ix_cutflow_handoff_artifact_id", table_name="cutflow_handoff")
    op.drop_index("ix_cutflow_handoff_variant_id", table_name="cutflow_handoff")
    op.drop_index("ix_cutflow_handoff_parent_task_id", table_name="cutflow_handoff")
    op.drop_index("ix_cutflow_handoff_user_id", table_name="cutflow_handoff")
    op.drop_table("cutflow_handoff")
