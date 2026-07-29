from dataclasses import dataclass
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from libtv_agent.domain.models import Base
from sqlalchemy import inspect
from sqlalchemy.engine import Connection


@dataclass(frozen=True)
class DatabaseSchemaStatus:
    ready: bool
    current_revisions: tuple[str, ...]
    expected_revisions: tuple[str, ...]
    missing_tables: tuple[str, ...]


def _expected_revisions() -> tuple[str, ...]:
    backend_root = Path(__file__).resolve().parents[3]
    config = Config(str(backend_root / "alembic.ini"))
    return tuple(sorted(ScriptDirectory.from_config(config).get_heads()))


def inspect_database_schema(connection: Connection) -> DatabaseSchemaStatus:
    inspector = inspect(connection)
    table_names = set(inspector.get_table_names())
    expected_tables = set(Base.metadata.tables)
    missing_tables = tuple(sorted(expected_tables - table_names))
    expected_revisions = _expected_revisions()

    if "alembic_version" in table_names:
        current_revisions = tuple(
            sorted(MigrationContext.configure(connection).get_current_heads())
        )
        revisions_match = current_revisions == expected_revisions
    else:
        # Unit-test and disposable databases may be initialized with
        # Base.metadata.create_all() instead of Alembic.
        current_revisions = ()
        revisions_match = not missing_tables

    return DatabaseSchemaStatus(
        ready=revisions_match and not missing_tables,
        current_revisions=current_revisions,
        expected_revisions=expected_revisions,
        missing_tables=missing_tables,
    )
