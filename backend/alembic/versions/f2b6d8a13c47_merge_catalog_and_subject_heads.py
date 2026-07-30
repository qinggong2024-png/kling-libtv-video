"""merge editable catalog and subject element migrations

Revision ID: f2b6d8a13c47
Revises: 7e12c4a9b631, e8c1a4b7d930
Create Date: 2026-07-30 00:00:00
"""

from collections.abc import Sequence

revision: str = "f2b6d8a13c47"
down_revision: str | Sequence[str] | None = ("7e12c4a9b631", "e8c1a4b7d930")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
