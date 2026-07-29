"""add user prompt confirmation preference

Revision ID: 4a27d8c91e53
Revises: 6f49b0f613d2
Create Date: 2026-07-29 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4a27d8c91e53"
down_revision: str | None = "6f49b0f613d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "app_user",
        sa.Column("auto_confirm_prompts", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("app_user", "auto_confirm_prompts")
