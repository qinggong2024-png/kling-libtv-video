"""merge pilot controls and product foundation migration heads

Revision ID: c9f0a1b2c304
Revises: c8d4e6f1a203, c8e4f1a2b907
Create Date: 2026-10-06 00:00:00.000000
"""

from collections.abc import Sequence

revision: str = "c9f0a1b2c304"
down_revision: str | Sequence[str] | None = ("c8d4e6f1a203", "c8e4f1a2b907")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
