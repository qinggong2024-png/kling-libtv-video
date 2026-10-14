"""Merge the phase repair with the current production schema."""

revision = "ca01b2c3d406"
# env.py schedules the capacity branch before the historical approval update.
down_revision = ("ca01b2c3d405", "c9f0a1b2c3d4")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
