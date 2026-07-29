"""Initial task and built-in authentication tables.

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

user_role = sa.Enum("USER", "TRUSTED_USER", "OPERATOR", "ADMIN", "AUDITOR", name="userrole")
task_status = sa.Enum(
    "DRAFT",
    "ANALYZING",
    "AWAITING_CONFIRMATION",
    "PREPARING",
    "GENERATING",
    "PARTIALLY_DELIVERABLE",
    "DELIVERABLE",
    "ACTION_REQUIRED",
    "CANCELLED",
    name="parenttaskstatus",
)
variant_kind = sa.Enum("STABLE", "DYNAMIC", name="variantkind")
generation_status = sa.Enum(
    "PENDING", "RUNNING", "SUCCEEDED", "FAILED", "UNKNOWN", name="generationstatus"
)
download_status = sa.Enum(
    "NOT_READY", "QUEUED", "DOWNLOADING", "READY", "FAILED", name="downloadstatus"
)
validation_status = sa.Enum(
    "NOT_READY",
    "TECHNICAL_CHECKING",
    "AI_CHECKING",
    "PASSED",
    "WARNING",
    "FAILED",
    "MANUAL_REVIEW",
    name="validationstatus",
)


def upgrade() -> None:
    op.create_table(
        "app_user",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", user_role, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_app_user_username", "app_user", ["username"], unique=True)
    op.create_table(
        "user_session",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_session_token_hash", "user_session", ["token_hash"], unique=True)
    op.create_index("ix_user_session_expires_at", "user_session", ["expires_at"])
    op.create_table(
        "parent_task",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("asset_count", sa.Integer(), nullable=False),
        sa.Column("user_requirement", sa.Text(), nullable=False),
        sa.Column("status", task_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint("asset_count BETWEEN 1 AND 7", name="ck_parent_task_asset_count"),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_parent_task_status", "parent_task", ["status"])
    op.create_table(
        "generation_variant",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("parent_task_id", sa.Uuid(), nullable=False),
        sa.Column("kind", variant_kind, nullable=False),
        sa.Column("generation_status", generation_status, nullable=False),
        sa.Column("download_status", download_status, nullable=False),
        sa.Column("validation_status", validation_status, nullable=False),
        sa.ForeignKeyConstraint(["parent_task_id"], ["parent_task.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("parent_task_id", "kind", name="uq_generation_variant_task_kind"),
    )
    op.create_index(
        "ix_generation_variant_parent_task_id", "generation_variant", ["parent_task_id"]
    )


def downgrade() -> None:
    op.drop_table("generation_variant")
    op.drop_table("parent_task")
    op.drop_table("user_session")
    op.drop_table("app_user")
    validation_status.drop(op.get_bind())
    download_status.drop(op.get_bind())
    generation_status.drop(op.get_bind())
    variant_kind.drop(op.get_bind())
    task_status.drop(op.get_bind())
    user_role.drop(op.get_bind())
