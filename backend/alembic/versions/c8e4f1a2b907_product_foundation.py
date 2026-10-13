"""add product and immutable product version foundation

Revision ID: c8e4f1a2b907
Revises: b7d9e1f3a502
Create Date: 2026-08-11 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c8e4f1a2b907"
down_revision: str | None = "b7d9e1f3a502"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("internal_sku_id", sa.String(length=160), nullable=False),
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
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "internal_sku_id", name="uq_product_user_sku"),
    )
    op.create_index(
        "ix_product_user_id",
        "product",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_product_user_updated",
        "product",
        ["user_id", "updated_at", "id"],
        unique=False,
    )

    op.create_table(
        "product_version",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("product_page_url", sa.String(length=1000), nullable=False),
        sa.Column("page_title", sa.String(length=500), nullable=True),
        sa.Column(
            "candidate_names",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "truth_fields",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "immutable_fields",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "allowed_variation",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "source_asset_references",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "license_status",
            sa.Enum(
                "UNKNOWN",
                "VERIFIED",
                "BLOCKED",
                name="productlicensestatus",
                native_enum=False,
            ),
            nullable=False,
            server_default="UNKNOWN",
        ),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT",
                "READY",
                "APPROVED",
                "BLOCKED",
                name="productversionstatus",
                native_enum=False,
            ),
            nullable=False,
            server_default="DRAFT",
        ),
        sa.Column("blocked_reason", sa.String(length=500), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "version_number", name="uq_product_version_number"),
    )
    op.create_index(
        "ix_product_version_product_id",
        "product_version",
        ["product_id"],
        unique=False,
    )
    op.create_index(
        "ix_product_version_product_created",
        "product_version",
        ["product_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_product_version_license_status",
        "product_version",
        ["license_status"],
        unique=False,
    )
    op.create_index(
        "ix_product_version_status",
        "product_version",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_product_version_status", table_name="product_version")
    op.drop_index("ix_product_version_license_status", table_name="product_version")
    op.drop_index("ix_product_version_product_created", table_name="product_version")
    op.drop_index("ix_product_version_product_id", table_name="product_version")
    op.drop_table("product_version")
    op.drop_index("ix_product_user_updated", table_name="product")
    op.drop_index("ix_product_user_id", table_name="product")
    op.drop_table("product")
