"""Add durable WaveSpeed image generation batches.

Revision ID: 3a7c9e1f5b20
Revises: c1f8a2d4e6b0
Create Date: 2026-07-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3a7c9e1f5b20"
down_revision: str | Sequence[str] | None = "c1f8a2d4e6b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "image_generation_batch",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("client_batch_id", sa.String(length=160), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("expected_generation_count", sa.Integer(), nullable=False),
        sa.Column("paid_submission_consent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("error_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_image_batch_user_idempotency"),
    )
    op.create_index("ix_image_generation_batch_user_id", "image_generation_batch", ["user_id"])
    op.create_index("ix_image_generation_batch_status", "image_generation_batch", ["status"])
    op.create_index(
        "ix_image_batch_user_created", "image_generation_batch", ["user_id", "created_at"]
    )

    op.create_table(
        "image_generation_item",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("order_no", sa.Integer(), nullable=False),
        sa.Column("client_task_id", sa.String(length=160), nullable=False),
        sa.Column("outfit_id", sa.String(length=160), nullable=False),
        sa.Column("outfit_name", sa.String(length=160), nullable=False),
        sa.Column("sku", sa.String(length=160), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("view", sa.String(length=24), nullable=False),
        sa.Column("label", sa.String(length=160), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("model_id", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("provider_task_id", sa.String(length=160), nullable=True),
        sa.Column("provider_result_url", sa.Text(), nullable=True),
        sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("raw_response_json", sa.JSON(), nullable=True),
        sa.Column("error_json", sa.JSON(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["batch_id"], ["image_generation_batch.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_id", "order_no", name="uq_image_item_batch_order"),
    )
    op.create_index("ix_image_generation_item_batch_id", "image_generation_item", ["batch_id"])
    op.create_index("ix_image_generation_item_status", "image_generation_item", ["status"])
    op.create_index("ix_image_item_provider_task", "image_generation_item", ["provider_task_id"])

    op.create_table(
        "image_generation_output",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("order_no", sa.Integer(), nullable=False),
        sa.Column("remote_url", sa.Text(), nullable=False),
        sa.Column("object_key", sa.String(length=500), nullable=True),
        sa.Column("content_type", sa.String(length=80), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["item_id"], ["image_generation_item.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("item_id", "order_no", name="uq_image_output_item_order"),
    )
    op.create_index("ix_image_generation_output_item_id", "image_generation_output", ["item_id"])


def downgrade() -> None:
    op.drop_index("ix_image_generation_output_item_id", table_name="image_generation_output")
    op.drop_table("image_generation_output")
    op.drop_index("ix_image_item_provider_task", table_name="image_generation_item")
    op.drop_index("ix_image_generation_item_status", table_name="image_generation_item")
    op.drop_index("ix_image_generation_item_batch_id", table_name="image_generation_item")
    op.drop_table("image_generation_item")
    op.drop_index("ix_image_batch_user_created", table_name="image_generation_batch")
    op.drop_index("ix_image_generation_batch_status", table_name="image_generation_batch")
    op.drop_index("ix_image_generation_batch_user_id", table_name="image_generation_batch")
    op.drop_table("image_generation_batch")
