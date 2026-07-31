"""Allow partial generation results on PostgreSQL.

Revision ID: d1e7a3c5f902
Revises: b6f4d2a9c801
Create Date: 2026-07-31
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d1e7a3c5f902"
down_revision: str | Sequence[str] | None = "b6f4d2a9c801"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "ALTER TYPE generationstatus ADD VALUE IF NOT EXISTS 'PARTIAL' AFTER 'SUCCEEDED'"
        )


def downgrade() -> None:
    # PostgreSQL enum values cannot be removed safely while rows may reference them.
    # The base migration still drops the complete enum during a full downgrade.
    pass
