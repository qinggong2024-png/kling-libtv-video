"""phase two retention evidence

Revision ID: 8b91c2d45a10
Revises: f59dc2804e6f
Create Date: 2026-07-27 10:25:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8b91c2d45a10"
down_revision: str | None = "f59dc2804e6f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "download_artifact",
        sa.Column("deletion_pending_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "download_artifact",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "operational_metric_sample",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("runner_host_id", sa.Uuid(), nullable=False),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deployment_id", sa.String(length=80), nullable=False),
        sa.Column("libtv_adapter_mode", sa.String(length=20), nullable=False),
        sa.Column("global_slots", sa.Integer(), nullable=False),
        sa.Column("backlog_count", sa.Integer(), nullable=False),
        sa.Column("running_count", sa.Integer(), nullable=False),
        sa.Column("slot_utilization", sa.Float(), nullable=False),
        sa.Column("orphan_process_count", sa.Integer(), nullable=False),
        sa.Column("free_disk_percent", sa.Float(), nullable=False),
        sa.Column("global_paused", sa.Boolean(), nullable=False),
        sa.Column("paid_submissions_paused", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["runner_host_id"], ["runner_host.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_operational_metric_sample_captured_at"),
        "operational_metric_sample",
        ["captured_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_operational_metric_sample_deployment_id"),
        "operational_metric_sample",
        ["deployment_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_operational_metric_sample_libtv_adapter_mode"),
        "operational_metric_sample",
        ["libtv_adapter_mode"],
        unique=False,
    )
    op.create_index(
        op.f("ix_operational_metric_sample_runner_host_id"),
        "operational_metric_sample",
        ["runner_host_id"],
        unique=False,
    )
    op.create_index(
        "ix_operational_sample_host_time",
        "operational_metric_sample",
        ["runner_host_id", "captured_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_operational_sample_host_time", table_name="operational_metric_sample")
    op.drop_index(
        op.f("ix_operational_metric_sample_libtv_adapter_mode"),
        table_name="operational_metric_sample",
    )
    op.drop_index(
        op.f("ix_operational_metric_sample_deployment_id"),
        table_name="operational_metric_sample",
    )
    op.drop_index(
        op.f("ix_operational_metric_sample_runner_host_id"),
        table_name="operational_metric_sample",
    )
    op.drop_index(
        op.f("ix_operational_metric_sample_captured_at"),
        table_name="operational_metric_sample",
    )
    op.drop_table("operational_metric_sample")
    op.drop_column("download_artifact", "deleted_at")
    op.drop_column("download_artifact", "deletion_pending_at")
