"""persist MVP-4B Provider submission tickets.

The table is a durable admission record only. It deliberately has no foreign
keys to generation attempts, quota reservations, points ledgers, or Provider
tasks because this MVP does not create those records.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e4f5a6b7c809"
down_revision: str | Sequence[str] | None = "d2f3a4b5c607"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_submission_ticket",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("schema_version", sa.String(length=80), nullable=False),
        sa.Column("ticket_id", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("request_kind", sa.String(length=24), nullable=False),
        sa.Column("execution_mode", sa.String(length=32), nullable=False),
        sa.Column("future_adapter_action", sa.String(length=80), nullable=False),
        sa.Column("owner_id", sa.String(length=160), nullable=False),
        sa.Column("creative_task_id", sa.String(length=160), nullable=False),
        sa.Column("package_revision_id", sa.String(length=160), nullable=False),
        sa.Column("shot_id", sa.String(length=40), nullable=False),
        sa.Column("provider", sa.String(length=120), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("idempotency_key", sa.String(length=240), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("evidence_hash", sa.String(length=64), nullable=False),
        sa.Column("preflight_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("estimated_cost_micros", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("quota_units", sa.Integer(), nullable=False),
        sa.Column("manifest_path", sa.String(length=1000), nullable=False),
        sa.Column("manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("materialized_inputs_json", sa.JSON(), nullable=False),
        sa.Column("ticket_payload_json", sa.JSON(), nullable=False),
        sa.Column("invalidation_reason", sa.String(length=80), nullable=True),
        sa.Column("result_status", sa.String(length=32), nullable=True),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("provider_task_id", sa.String(length=200), nullable=True),
        sa.Column("response_digest", sa.String(length=64), nullable=True),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticket_id", name="uq_provider_submission_ticket_ticket_id"),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_provider_submission_ticket_idempotency_key",
        ),
    )
    op.create_index(
        "ix_provider_submission_ticket_status",
        "provider_submission_ticket",
        ["status"],
    )
    op.create_index(
        "ix_provider_submission_ticket_owner_status",
        "provider_submission_ticket",
        ["owner_id", "status"],
    )
    op.create_index(
        "ix_provider_submission_ticket_task_status",
        "provider_submission_ticket",
        ["creative_task_id", "status"],
    )
    op.create_index(
        "ix_provider_submission_ticket_expires_at",
        "provider_submission_ticket",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_provider_submission_ticket_expires_at",
        table_name="provider_submission_ticket",
    )
    op.drop_index(
        "ix_provider_submission_ticket_task_status",
        table_name="provider_submission_ticket",
    )
    op.drop_index(
        "ix_provider_submission_ticket_owner_status",
        table_name="provider_submission_ticket",
    )
    op.drop_index(
        "ix_provider_submission_ticket_status",
        table_name="provider_submission_ticket",
    )
    op.drop_table("provider_submission_ticket")

