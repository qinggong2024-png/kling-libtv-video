import os
import warnings

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from sqlalchemy import event  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402

# --- Why the pragma listener below exists -----------------------------------
#
# The suite builds ~90 throwaway SQLite databases per full run, most of them
# under ``tmp_path`` (i.e. the ``TEMP`` volume).  Python's sqlite3 driver only
# opens an implicit transaction for DML, never for DDL, so every
# ``CREATE TABLE`` emitted by ``Base.metadata.create_all`` autocommits on its
# own: each statement creates, fsyncs and deletes its own rollback journal.
# With 37 tables per database that is 37 journal round-trips per test, and on a
# ``TEMP`` directory that sits on a slow volume (or under real-time AV
# scanning) a single ``create_all`` cost 12-14 seconds.
#
# Measured with the same 37-table metadata before/after this listener:
#
#     F:\Temp (pytest tmp_path)   default pragmas  12.62s  ->  0.12s
#     E: repo volume              default pragmas   2.27s  ->  0.13s
#
# Nothing in the suite asserts on journal or durability semantics - the
# databases are per-test scratch data - so MEMORY/synchronous=OFF is safe here
# and must never be copied into application code.
#
# The listener is registered on the ``Engine`` class rather than on a specific
# engine, because each test module builds its own engines.  Non-SQLite
# connections (the optional G1_TEST_POSTGRES_URL / PHASE2_ONLINE_TESTS paths
# in test_image_quota_concurrency.py and test_online_infrastructure.py) are
# left untouched.

_SQLITE_DBAPI_MARKERS = ("sqlite3", "aiosqlite")
_pragma_warning_emitted = False


@event.listens_for(Engine, "connect")
def _apply_sqlite_test_pragmas(dbapi_connection, connection_record) -> None:  # noqa: ANN001
    global _pragma_warning_emitted
    module = type(dbapi_connection).__module__
    if not any(marker in module for marker in _SQLITE_DBAPI_MARKERS):
        return
    try:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=MEMORY")
            cursor.execute("PRAGMA synchronous=OFF")
        finally:
            cursor.close()
    except Exception as exc:  # noqa: BLE001 - a failed optimisation must not fail the suite
        if not _pragma_warning_emitted:
            _pragma_warning_emitted = True
            warnings.warn(
                f"could not apply SQLite test pragmas, tests will be slow: {exc!r}",
                stacklevel=1,
            )
