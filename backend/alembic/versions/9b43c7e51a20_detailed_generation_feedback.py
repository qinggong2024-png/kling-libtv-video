"""add detailed generation feedback

Revision ID: 9b43c7e51a20
Revises: 4a27d8c91e53
Create Date: 2026-07-29 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9b43c7e51a20"
down_revision: str | None = "4a27d8c91e53"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("generation_feedback") as batch_op:
        batch_op.add_column(
            sa.Column("reason_codes_json", sa.JSON(), nullable=False, server_default="[]")
        )
        batch_op.add_column(sa.Column("comment", sa.String(length=240), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("generation_feedback") as batch_op:
        batch_op.drop_column("comment")
        batch_op.drop_column("reason_codes_json")
