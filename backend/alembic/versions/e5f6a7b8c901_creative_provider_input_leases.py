"""persist Creative Provider input leases."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c901"
down_revision: str | Sequence[str] | None = "e4f5a6b7c809"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_input_lease",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("schema_version", sa.String(length=80), nullable=False),
        sa.Column("lease_id", sa.String(length=160), nullable=False),
        sa.Column("ticket_id", sa.String(length=160), nullable=False),
        sa.Column("idempotency_key", sa.String(length=240), nullable=False),
        sa.Column("owner_id", sa.String(length=160), nullable=False),
        sa.Column("creative_task_id", sa.String(length=160), nullable=False),
        sa.Column("package_revision_id", sa.String(length=160), nullable=False),
        sa.Column("shot_id", sa.String(length=40), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("evidence_hash", sa.String(length=64), nullable=False),
        sa.Column("request_kind", sa.String(length=24), nullable=False),
        sa.Column("execution_mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("manifest_json", sa.JSON(), nullable=False),
        sa.Column("source_ticket_hash", sa.String(length=64), nullable=False),
        sa.Column("invalidation_reason", sa.String(length=120), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lease_id", name="uq_provider_input_lease_lease_id"),
        sa.UniqueConstraint("ticket_id", name="uq_provider_input_lease_ticket_id"),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_provider_input_lease_idempotency_key",
        ),
    )
    op.create_index(
        "ix_provider_input_lease_status",
        "provider_input_lease",
        ["status"],
    )
    op.create_index(
        "ix_provider_input_lease_owner_status",
        "provider_input_lease",
        ["owner_id", "status"],
    )
    op.create_index(
        "ix_provider_input_lease_creative_task_id",
        "provider_input_lease",
        ["creative_task_id"],
    )
    op.create_index(
        "ix_provider_input_lease_expires_at",
        "provider_input_lease",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_provider_input_lease_expires_at",
        table_name="provider_input_lease",
    )
    op.drop_index(
        "ix_provider_input_lease_creative_task_id",
        table_name="provider_input_lease",
    )
    op.drop_index(
        "ix_provider_input_lease_owner_status",
        table_name="provider_input_lease",
    )
    op.drop_index(
        "ix_provider_input_lease_status",
        table_name="provider_input_lease",
    )
    op.drop_table("provider_input_lease")
