"""Widen parent phase before the historical final-approval data update."""

import sqlalchemy as sa
from alembic import op

revision = "ca01b2c3d405"
down_revision = "5c8f2a1d9e70"
branch_labels = None
depends_on = None


def order_upgrade_steps(steps):
    """Schedule this registered branch before the old data update it enables."""
    steps = list(steps)
    if not all(step.is_upgrade for step in steps):
        return steps
    ids = [step.revision.revision for step in steps]
    if revision in ids and "a6c8e2f4b901" in ids:
        repair_index = ids.index(revision)
        approval_index = ids.index("a6c8e2f4b901")
        if repair_index > approval_index:
            repair = steps.pop(repair_index)
            steps.insert(approval_index, repair)
    return steps


def upgrade() -> None:
    with op.batch_alter_table("parent_task") as batch:
        batch.alter_column(
            "phase",
            existing_type=sa.String(21),
            type_=sa.String(32),
            existing_nullable=False,
        )


def downgrade() -> None:
    # Narrowing could truncate states written by the historical approval branch.
    # Extra string capacity remains compatible with older application versions.
    pass
