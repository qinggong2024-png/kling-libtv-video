"""add fixed-template workflow metadata

Revision ID: 2d7f6a9b4c10
Revises: 9b43c7e51a20
Create Date: 2026-07-30 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2d7f6a9b4c10"
down_revision: str | None = "9b43c7e51a20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "staged_upload",
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "asset",
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "parent_task",
        sa.Column(
            "workflow_kind",
            sa.String(length=32),
            nullable=False,
            server_default="LEGACY_ANALYSIS",
        ),
    )
    op.add_column("parent_task", sa.Column("template_id", sa.String(length=80), nullable=True))
    op.add_column(
        "parent_task", sa.Column("template_version", sa.String(length=40), nullable=True)
    )
    op.add_column(
        "parent_task", sa.Column("site_profile_id", sa.String(length=80), nullable=True)
    )
    op.add_column(
        "parent_task", sa.Column("site_profile_version", sa.String(length=40), nullable=True)
    )
    op.add_column(
        "parent_task",
        sa.Column("settings_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column("parent_task", sa.Column("compiled_plan_json", sa.JSON(), nullable=True))
    op.add_column(
        "parent_task", sa.Column("material_validation_json", sa.JSON(), nullable=True)
    )
    op.add_column(
        "parent_task",
        sa.Column("paid_submission_consent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_parent_task_workflow_kind",
        "parent_task",
        ["workflow_kind"],
        unique=False,
    )
    op.create_index(
        "ix_parent_task_template_id",
        "parent_task",
        ["template_id"],
        unique=False,
    )
    op.create_index(
        "ix_parent_task_site_profile_id",
        "parent_task",
        ["site_profile_id"],
        unique=False,
    )

    op.add_column(
        "generation_variant", sa.Column("variant_index", sa.Integer(), nullable=True)
    )
    op.add_column(
        "generation_variant", sa.Column("variant_key", sa.String(length=80), nullable=True)
    )
    op.add_column(
        "generation_variant",
        sa.Column("variant_seed_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.create_index(
        "uq_generation_variant_task_index",
        "generation_variant",
        ["parent_task_id", "variant_index"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_generation_variant_task_index", table_name="generation_variant")
    op.drop_column("generation_variant", "variant_seed_json")
    op.drop_column("generation_variant", "variant_key")
    op.drop_column("generation_variant", "variant_index")

    op.drop_index("ix_parent_task_site_profile_id", table_name="parent_task")
    op.drop_index("ix_parent_task_template_id", table_name="parent_task")
    op.drop_index("ix_parent_task_workflow_kind", table_name="parent_task")
    op.drop_column("parent_task", "paid_submission_consent_at")
    op.drop_column("parent_task", "material_validation_json")
    op.drop_column("parent_task", "compiled_plan_json")
    op.drop_column("parent_task", "settings_json")
    op.drop_column("parent_task", "site_profile_version")
    op.drop_column("parent_task", "site_profile_id")
    op.drop_column("parent_task", "template_version")
    op.drop_column("parent_task", "template_id")
    op.drop_column("parent_task", "workflow_kind")
    op.drop_column("asset", "size_bytes")
    op.drop_column("staged_upload", "size_bytes")
