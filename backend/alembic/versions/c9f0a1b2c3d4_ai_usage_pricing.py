"""Versioned USD accounting without relabelling historical risk units."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9f0a1b2c3d4"
down_revision: str | Sequence[str] | None = "c8e9f0a1b2c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Server defaults mark old rows explicitly; current application writes V1.
    op.add_column("ai_usage_reservation", sa.Column(
        "accounting_version", sa.String(40), nullable=False, server_default="LEGACY_RISK_V0",
    ))
    op.add_column("ai_usage_reservation", sa.Column("business_date", sa.Date(), nullable=True))
    op.add_column("ai_usage_reservation", sa.Column(
        "estimated_cost_microusd", sa.BigInteger(), nullable=True,
    ))
    op.add_column("ai_usage_reservation", sa.Column(
        "actual_cost_microusd", sa.BigInteger(), nullable=True,
    ))
    op.add_column("ai_usage_reservation", sa.Column(
        "pricing_snapshot_json", sa.JSON(), nullable=True,
    ))
    op.add_column("ai_usage_ledger", sa.Column(
        "accounting_version", sa.String(40), nullable=False, server_default="LEGACY_RISK_V0",
    ))
    op.add_column("ai_usage_ledger", sa.Column("cost_microusd", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("ai_usage_ledger", "cost_microusd")
    op.drop_column("ai_usage_ledger", "accounting_version")
    for column in (
        "pricing_snapshot_json", "actual_cost_microusd", "estimated_cost_microusd",
        "business_date", "accounting_version",
    ):
        op.drop_column("ai_usage_reservation", column)
