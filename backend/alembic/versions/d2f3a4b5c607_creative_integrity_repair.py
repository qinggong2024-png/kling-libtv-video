"""CW-3E repair for immutable product facts and creative commands."""
import sqlalchemy as sa
from alembic import op

revision = "d2f3a4b5c607"
down_revision = "d1e2f3a4b506"
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute(sa.text(
            "CREATE TRIGGER product_version_facts_no_delete "
            "BEFORE DELETE ON product_version "
            "BEGIN SELECT RAISE(ABORT, 'immutable product facts'); END"
        ))
        op.execute(sa.text(
            "CREATE TRIGGER creative_command_no_update "
            "BEFORE UPDATE ON creative_command "
            "BEGIN SELECT RAISE(ABORT, 'immutable creative command'); END"
        ))
        op.execute(sa.text(
            "CREATE TRIGGER creative_command_no_delete "
            "BEFORE DELETE ON creative_command "
            "BEGIN SELECT RAISE(ABORT, 'immutable creative command'); END"
        ))
    elif dialect == "postgresql":
        op.execute(sa.text(
            "CREATE FUNCTION cw3e_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ "
            "BEGIN RAISE EXCEPTION 'immutable creative history'; END; $$"
        ))
        op.execute(sa.text(
            "CREATE TRIGGER product_version_facts_no_delete "
            "BEFORE DELETE ON product_version FOR EACH ROW "
            "EXECUTE FUNCTION cw3e_immutable()"
        ))
        op.execute(sa.text(
            "CREATE TRIGGER creative_command_no_update "
            "BEFORE UPDATE ON creative_command FOR EACH ROW "
            "EXECUTE FUNCTION cw3e_immutable()"
        ))
        op.execute(sa.text(
            "CREATE TRIGGER creative_command_no_delete "
            "BEFORE DELETE ON creative_command FOR EACH ROW "
            "EXECUTE FUNCTION cw3e_immutable()"
        ))


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute(sa.text(
            "DROP TRIGGER IF EXISTS product_version_facts_no_delete"
        ))
        op.execute(sa.text("DROP TRIGGER IF EXISTS creative_command_no_update"))
        op.execute(sa.text("DROP TRIGGER IF EXISTS creative_command_no_delete"))
    elif dialect == "postgresql":
        op.execute(sa.text(
            "DROP TRIGGER IF EXISTS product_version_facts_no_delete ON product_version"
        ))
        op.execute(sa.text(
            "DROP TRIGGER IF EXISTS creative_command_no_update ON creative_command"
        ))
        op.execute(sa.text(
            "DROP TRIGGER IF EXISTS creative_command_no_delete ON creative_command"
        ))
        op.execute(sa.text("DROP FUNCTION IF EXISTS cw3e_immutable()"))
