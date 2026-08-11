"""persist candidate qualification and final delivery approvals

Revision ID: a6c8e2f4b901
Revises: 5c8f2a1d9e70
Create Date: 2026-08-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a6c8e2f4b901"
down_revision: str | Sequence[str] | None = "5c8f2a1d9e70"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _quality_columns(table: str, *, approver_name: str) -> None:
    with op.batch_alter_table(table) as batch_op:
        batch_op.add_column(
            sa.Column(
                "quality_gates_json",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            )
        )
        batch_op.add_column(sa.Column(approver_name, sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("human_review_seconds", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("review_notes", sa.String(length=500), nullable=True))
        batch_op.create_foreign_key(
            f"fk_{table}_{approver_name}_app_user",
            "app_user",
            [approver_name],
            ["id"],
            ondelete="RESTRICT",
        )


def upgrade() -> None:
    op.add_column(
        "generation_variant",
        sa.Column(
            "final_approval_status",
            sa.String(length=24),
            nullable=False,
            server_default="PENDING",
        ),
    )
    _quality_columns("generation_variant", approver_name="final_approved_by")
    op.add_column(
        "generation_variant",
        sa.Column("final_approved_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.add_column(
        "image_generation_output",
        sa.Column(
            "qualification_status",
            sa.String(length=24),
            nullable=False,
            server_default="PENDING",
        ),
    )
    _quality_columns("image_generation_output", approver_name="reviewed_by")
    op.add_column(
        "image_generation_output",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Historical technical completions are intentionally not grandfathered into Deliverable.
    # They require explicit Ground Truth under Production Acceptance Contract v1.3.
    op.execute(
        "UPDATE parent_task SET phase = 'AWAITING_FINAL_APPROVAL', "
        "phase_reason_code = 'FINAL_APPROVAL_REQUIRED' WHERE phase = 'DELIVERABLE'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE parent_task SET phase = 'ACTION_REQUIRED', "
        "phase_reason_code = 'FINAL_APPROVAL_DATA_REMOVED' "
        "WHERE phase = 'AWAITING_FINAL_APPROVAL'"
    )
    op.drop_column("image_generation_output", "reviewed_at")
    with op.batch_alter_table("image_generation_output") as batch_op:
        batch_op.drop_constraint(
            "fk_image_generation_output_reviewed_by_app_user", type_="foreignkey"
        )
        batch_op.drop_column("review_notes")
        batch_op.drop_column("human_review_seconds")
        batch_op.drop_column("reviewed_by")
        batch_op.drop_column("quality_gates_json")
    op.drop_column("image_generation_output", "qualification_status")

    op.drop_column("generation_variant", "final_approved_at")
    with op.batch_alter_table("generation_variant") as batch_op:
        batch_op.drop_constraint(
            "fk_generation_variant_final_approved_by_app_user", type_="foreignkey"
        )
        batch_op.drop_column("review_notes")
        batch_op.drop_column("human_review_seconds")
        batch_op.drop_column("final_approved_by")
        batch_op.drop_column("quality_gates_json")
    op.drop_column("generation_variant", "final_approval_status")
