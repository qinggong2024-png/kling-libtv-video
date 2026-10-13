"""CW-1 offline creative snapshots and idempotent commands."""
import sqlalchemy as sa
from alembic import op

revision = "d0c1e2f3a405"
down_revision = "c9f0a1b2c304"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "creative_task",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("product_id", sa.Uuid(), sa.ForeignKey("product.id"), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
    )
    op.create_index("ix_creative_task_user_id", "creative_task", ["user_id"])
    op.create_table(
        "creative_record",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("creative_task.id"), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("record_key", sa.String(160), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.UniqueConstraint("task_id", "kind", "record_key", name="uq_creative_record_key"),
    )
    op.create_index("ix_creative_record_task_id", "creative_record", ["task_id"])
    op.create_table(
        "creative_command",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("creative_task.id"), nullable=False),
        sa.Column("command_key", sa.String(120), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.UniqueConstraint("task_id", "command_key", name="uq_creative_command_key"),
    )
    op.create_index("ix_creative_command_task_id", "creative_command", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_creative_command_task_id", table_name="creative_command")
    op.drop_table("creative_command")
    op.drop_index("ix_creative_record_task_id", table_name="creative_record")
    op.drop_table("creative_record")
    op.drop_index("ix_creative_task_user_id", table_name="creative_task")
    op.drop_table("creative_task")
