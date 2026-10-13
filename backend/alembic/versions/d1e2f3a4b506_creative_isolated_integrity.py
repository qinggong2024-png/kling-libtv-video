"""CW2 upload product source, persistent creation identity and immutable prompt registry."""
import sqlalchemy as sa
from alembic import op

revision = "d1e2f3a4b506"
down_revision = "d0c1e2f3a405"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("product_version") as batch:
        batch.alter_column("product_page_url", existing_type=sa.String(1000), nullable=True)
        batch.add_column(sa.Column(
            "source_type", sa.String(32), nullable=False, server_default="PRODUCT_PAGE",
        ))
        batch.add_column(sa.Column("request_key", sa.String(120), nullable=True))
        batch.add_column(sa.Column("request_hash", sa.String(64), nullable=True))
        batch.create_unique_constraint(
            "uq_product_version_request_key", ["product_id", "request_key"],
        )
    op.create_table(
        "creative_creation",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("client_key", sa.String(120), nullable=False),
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("creative_task.id"), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.UniqueConstraint("user_id", "client_key", name="uq_creative_creation_owner_key"),
        sa.UniqueConstraint("task_id"),
    )
    op.create_index("ix_creative_creation_user_id", "creative_creation", ["user_id"])
    op.create_table(
        "creative_prompt_registry",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("prompt_key", sa.String(80), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.UniqueConstraint("prompt_key", "version", name="uq_creative_prompt_registry_version"),
    )
    # History is protected at the database boundary, including non-ORM writers.
    if op.get_bind().dialect.name == "sqlite":
        for table in ("creative_record", "creative_prompt_registry", "creative_creation"):
            for action in ("UPDATE", "DELETE"):
                op.execute(sa.text(
                    f"CREATE TRIGGER {table}_no_{action.lower()} BEFORE {action} ON {table} "
                    "BEGIN SELECT RAISE(ABORT, 'immutable creative history'); END"
                ))
        op.execute(sa.text(
            "CREATE TRIGGER product_version_facts_no_update BEFORE UPDATE OF "
            "product_id,version_number,product_page_url,source_type,page_title,candidate_names,"
            "truth_fields,immutable_fields,allowed_variation,source_asset_references,"
            "request_key,request_hash ON product_version "
            "BEGIN SELECT RAISE(ABORT, 'immutable product facts'); END"
        ))
    elif op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text(
            "CREATE FUNCTION cw2_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ "
            "BEGIN RAISE EXCEPTION 'immutable creative history'; END; $$"
        ))
        for table in ("creative_record", "creative_prompt_registry", "creative_creation"):
            op.execute(sa.text(
                f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION cw2_immutable()"
            ))
        op.execute(sa.text(
            "CREATE TRIGGER product_version_facts_immutable BEFORE UPDATE OF "
            "product_id,version_number,product_page_url,source_type,page_title,candidate_names,"
            "truth_fields,immutable_fields,allowed_variation,source_asset_references,"
            "request_key,request_hash ON product_version "
            "FOR EACH ROW EXECUTE FUNCTION cw2_immutable()"
        ))


def downgrade() -> None:
    if op.get_bind().execute(sa.text(
        "SELECT 1 FROM product_version WHERE product_page_url IS NULL LIMIT 1",
    )).first():
        raise RuntimeError("Cannot downgrade upload versions without a real URL")
    if op.get_bind().dialect.name == "sqlite":
        for table in ("creative_record", "creative_prompt_registry", "creative_creation"):
            for action in ("update", "delete"):
                op.execute(sa.text(f"DROP TRIGGER IF EXISTS {table}_no_{action}"))
        op.execute(sa.text("DROP TRIGGER IF EXISTS product_version_facts_no_update"))
    elif op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("DROP FUNCTION cw2_immutable() CASCADE"))
    op.drop_table("creative_prompt_registry")
    op.drop_index("ix_creative_creation_user_id", table_name="creative_creation")
    op.drop_table("creative_creation")
    with op.batch_alter_table("product_version") as batch:
        batch.drop_constraint("uq_product_version_request_key", type_="unique")
        batch.drop_column("request_hash")
        batch.drop_column("request_key")
        batch.drop_column("source_type")
        batch.alter_column("product_page_url", existing_type=sa.String(1000), nullable=False)
