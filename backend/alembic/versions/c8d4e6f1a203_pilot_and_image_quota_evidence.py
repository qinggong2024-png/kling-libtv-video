"""add internal pilot controls and image quota evidence

Revision ID: c8d4e6f1a203
Revises: b7d9e1f3a502
Create Date: 2026-10-06 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c8d4e6f1a203"
down_revision: str | None = "b7d9e1f3a502"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "image_quota_reservation",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("estimated_images", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("unknown_reason", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["batch_id"], ["image_generation_batch.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_id"),
    )
    op.create_index(
        "ix_image_quota_reservation_batch_id",
        "image_quota_reservation",
        ["batch_id"],
        unique=True,
    )
    op.create_index(
        "ix_image_quota_reservation_user_id",
        "image_quota_reservation",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_image_quota_reservation_business_date",
        "image_quota_reservation",
        ["business_date"],
        unique=False,
    )
    op.create_index(
        "ix_image_quota_reservation_status",
        "image_quota_reservation",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_image_quota_reservation_status", table_name="image_quota_reservation")
    op.drop_index(
        "ix_image_quota_reservation_business_date",
        table_name="image_quota_reservation",
    )
    op.drop_index("ix_image_quota_reservation_user_id", table_name="image_quota_reservation")
    op.drop_index("ix_image_quota_reservation_batch_id", table_name="image_quota_reservation")
    op.drop_table("image_quota_reservation")
