"""add editable content catalog

Revision ID: 7e12c4a9b631
Revises: d9e2f3a4b5c6
Create Date: 2026-07-30 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7e12c4a9b631"
down_revision: str | None = "d9e2f3a4b5c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "catalog_entry",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("entry_type", sa.String(length=32), nullable=False),
        sa.Column("entry_id", sa.String(length=80), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["updated_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entry_type", "entry_id", name="uq_catalog_entry_type_id"),
    )
    op.create_index(
        "ix_catalog_entry_type_updated",
        "catalog_entry",
        ["entry_type", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_catalog_entry_type_updated", table_name="catalog_entry")
    op.drop_table("catalog_entry")
