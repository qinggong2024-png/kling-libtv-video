"""Add persistent AI risk-unit reservations and ledger.

Revision ID: c8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c8e9f0a1b2c3"
down_revision: str | Sequence[str] | None = "c7d8e9f0a1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_usage_reservation",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("operation_type", sa.String(length=60), nullable=False),
        sa.Column("provider", sa.String(length=60), nullable=False),
        sa.Column("model", sa.String(length=160), nullable=False),
        sa.Column("input_chars", sa.Integer(), nullable=False),
        sa.Column("input_image_count", sa.Integer(), nullable=False),
        sa.Column("max_output_tokens", sa.Integer(), nullable=False),
        sa.Column("risk_units", sa.Integer(), nullable=False),
        sa.Column("actual_input_tokens", sa.Integer(), nullable=True),
        sa.Column("actual_output_tokens", sa.Integer(), nullable=True),
        sa.Column("actual_risk_units", sa.Integer(), nullable=True),
        sa.Column("actual_cost_status", sa.String(length=40), nullable=False),
        sa.Column("provider_response_id", sa.String(length=255), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["parent_task.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "operation_type",
            "idempotency_key",
            name="uq_ai_usage_reservation_request",
        ),
    )
    op.create_index(
        "ix_ai_usage_reservation_user_id",
        "ai_usage_reservation",
        ["user_id"],
    )
    op.create_index(
        "ix_ai_usage_reservation_task_id",
        "ai_usage_reservation",
        ["task_id"],
    )
    op.create_index(
        "ix_ai_usage_reservation_user_created",
        "ai_usage_reservation",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_ai_usage_reservation_status",
        "ai_usage_reservation",
        ["status"],
    )

    op.create_table(
        "ai_usage_quota_summary",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scope_key", sa.String(length=80), nullable=False),
        sa.Column("scope_type", sa.String(length=20), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("limit_units", sa.Integer(), nullable=False),
        sa.Column("reserved_units", sa.Integer(), nullable=False),
        sa.Column("consumed_units", sa.Integer(), nullable=False),
        sa.Column("unknown_units", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope_key", "business_date", name="uq_ai_usage_scope_date"),
    )
    op.create_index(
        "ix_ai_usage_quota_summary_user_id",
        "ai_usage_quota_summary",
        ["user_id"],
    )
    op.create_index(
        "ix_ai_usage_quota_summary_business_date",
        "ai_usage_quota_summary",
        ["business_date"],
    )
    op.create_index(
        "ix_ai_usage_quota_user_date",
        "ai_usage_quota_summary",
        ["user_id", "business_date"],
    )

    op.create_table(
        "ai_usage_ledger",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("reservation_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("operation_type", sa.String(length=60), nullable=False),
        sa.Column("entry_type", sa.String(length=20), nullable=False),
        sa.Column("risk_units", sa.Integer(), nullable=False),
        sa.Column("actual_input_tokens", sa.Integer(), nullable=True),
        sa.Column("actual_output_tokens", sa.Integer(), nullable=True),
        sa.Column("actual_cost_status", sa.String(length=40), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["reservation_id"], ["ai_usage_reservation.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["task_id"], ["parent_task.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_usage_ledger_reservation_id",
        "ai_usage_ledger",
        ["reservation_id"],
    )
    op.create_index(
        "ix_ai_usage_ledger_user_id",
        "ai_usage_ledger",
        ["user_id"],
    )
    op.create_index(
        "ix_ai_usage_ledger_task_id",
        "ai_usage_ledger",
        ["task_id"],
    )
    op.create_index(
        "ix_ai_usage_ledger_reservation_created",
        "ai_usage_ledger",
        ["reservation_id", "created_at"],
    )
    op.create_index(
        "ix_ai_usage_ledger_user_created",
        "ai_usage_ledger",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_usage_ledger_user_created", table_name="ai_usage_ledger")
    op.drop_index("ix_ai_usage_ledger_reservation_created", table_name="ai_usage_ledger")
    op.drop_index("ix_ai_usage_ledger_task_id", table_name="ai_usage_ledger")
    op.drop_index("ix_ai_usage_ledger_user_id", table_name="ai_usage_ledger")
    op.drop_index("ix_ai_usage_ledger_reservation_id", table_name="ai_usage_ledger")
    op.drop_table("ai_usage_ledger")

    op.drop_index("ix_ai_usage_quota_user_date", table_name="ai_usage_quota_summary")
    op.drop_index("ix_ai_usage_quota_summary_business_date", table_name="ai_usage_quota_summary")
    op.drop_index("ix_ai_usage_quota_summary_user_id", table_name="ai_usage_quota_summary")
    op.drop_table("ai_usage_quota_summary")

    op.drop_index("ix_ai_usage_reservation_status", table_name="ai_usage_reservation")
    op.drop_index("ix_ai_usage_reservation_user_created", table_name="ai_usage_reservation")
    op.drop_index("ix_ai_usage_reservation_task_id", table_name="ai_usage_reservation")
    op.drop_index("ix_ai_usage_reservation_user_id", table_name="ai_usage_reservation")
    op.drop_table("ai_usage_reservation")
