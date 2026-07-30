"""Persist structured provider error metadata.

Revision ID: d9e2f3a4b5c6
Revises: 2d7f6a9b4c10
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d9e2f3a4b5c6"
down_revision: str | Sequence[str] | None = "2d7f6a9b4c10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "generation_attempt",
        sa.Column("provider_error_details_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "generation_attempt",
        sa.Column("provider_error_retryable", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("generation_attempt", "provider_error_retryable")
    op.drop_column("generation_attempt", "provider_error_details_json")
