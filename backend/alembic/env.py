from logging.config import fileConfig

from alembic import context
from libtv_agent.config import get_settings
from libtv_agent.domain.models import Base
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata


def configure_migrations(**kwargs) -> None:
    context.configure(**kwargs)
    original = context.get_context().opts.get("fn")
    if original is None:
        return
    repair = context.script.get_revision("ca01b2c3d405").module

    def ordered_steps(revisions, migration_context):
        # Execute and version every normal Alembic step; only move the new
        # capacity branch ahead of the historical update requiring that width.
        return repair.order_upgrade_steps(original(revisions, migration_context))

    context.configure(**kwargs, fn=ordered_steps)


def run_migrations_offline() -> None:
    configure_migrations(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: object) -> None:
    configure_migrations(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
elif config.attributes.get("connection") is not None:
    do_run_migrations(config.attributes["connection"])
else:
    import asyncio

    asyncio.run(run_migrations_online())
