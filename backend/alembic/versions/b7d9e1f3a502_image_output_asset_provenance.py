"""Preserve qualified image-output provenance through video assets.

Revision ID: b7d9e1f3a502
Revises: a6c8e2f4b901
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7d9e1f3a502"
down_revision: str | Sequence[str] | None = "a6c8e2f4b901"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("staged_upload") as batch_op:
        batch_op.add_column(sa.Column("source_image_output_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_staged_upload_source_image_output",
            "image_generation_output",
            ["source_image_output_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_staged_upload_source_image_output_id", ["source_image_output_id"])
    with op.batch_alter_table("asset") as batch_op:
        batch_op.add_column(sa.Column("source_image_output_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_asset_source_image_output",
            "image_generation_output",
            ["source_image_output_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_asset_source_image_output_id", ["source_image_output_id"])


def downgrade() -> None:
    with op.batch_alter_table("asset") as batch_op:
        batch_op.drop_index("ix_asset_source_image_output_id")
        batch_op.drop_constraint("fk_asset_source_image_output", type_="foreignkey")
        batch_op.drop_column("source_image_output_id")
    with op.batch_alter_table("staged_upload") as batch_op:
        batch_op.drop_index("ix_staged_upload_source_image_output_id")
        batch_op.drop_constraint("fk_staged_upload_source_image_output", type_="foreignkey")
        batch_op.drop_column("source_image_output_id")
