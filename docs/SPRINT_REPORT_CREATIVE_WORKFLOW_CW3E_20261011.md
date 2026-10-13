# Sprint Report: Creative Workflow CW-3E

Date: 2026-10-11
Scope: append-only Alembic repair for immutable creative records

## Completed

- Added migration `d2f3a4b5c607`, with `down_revision=d1e2f3a4b506`.
- Added SQLite `product_version_facts_no_delete`, `creative_command_no_update`, and
  `creative_command_no_delete` BEFORE triggers using `RAISE(ABORT, ...)`.
- Added PostgreSQL equivalents using the independent `cw3e_immutable()` function.
- Downgrade removes only the d2 triggers and function; it does not remove d1
  triggers or the d1 `cw2_immutable()` function.
- Added real Alembic temporary-SQLite coverage for old rows, fact hashes,
  ProductVersion UPDATE/DELETE, CreativeCommand UPDATE/DELETE, old
  CreativeRecord/Prompt/Creation protections, USER_UPLOAD null URLs,
  request-key uniqueness, and d2-to-d1 downgrade behavior.

## Files

Added:

- `backend/alembic/versions/d2f3a4b5c607_creative_integrity_repair.py`
- `backend/tests/test_creative_migration_repair.py`
- this report

Not modified:

- `d1e2f3a4b506_creative_isolated_integrity.py`
- CW-3D test, runner, shared conftest, ORM, schema, API, OpenAPI, and model files

## Testing

Testing branch (`E:\Projects\libtv自动化生成`, `codex/testing`):

```text
.venv/Scripts/python.exe -m ruff check backend/alembic/versions/d2f3a4b5c607_creative_integrity_repair.py backend/tests/test_creative_migration_repair.py
```

Result: PASS.

```text
.venv/Scripts/python.exe -m pytest backend/tests/test_creative_migration_repair.py -q
```

Result: `3 passed`, exit code 0.

Unmodified CW-3D regression:

```text
.venv/Scripts/python.exe -m pytest backend/tests/test_creative_migration_integrity.py -q
```

Result: `2 passed, 2 failed`, exit code 1. The two strict failures remain the
d1 missing ProductVersion DELETE and CreativeCommand DELETE protections; the
test was not changed or weakened.

## Hashes

Testing SHA-256 after implementation:

- `backend/alembic/versions/d2f3a4b5c607_creative_integrity_repair.py`:
  `6B5A617C3A2769D51C0CA7C8690CA0706D5BE3CC64D0000EC4DD7B96DBDD0185`
- `backend/tests/test_creative_migration_repair.py`:
  `5833C20727F4E99E9EBEAAAE6E64896FAF3FC8ADF35FCE49CE677A07B759AFC2`
- historical d1 migration remained:
  `D7F2D97EDD55F9F0A7FD0417DE8141CF14A454AE20788ED820F5418CC5F77631`

## Findings and limits

- PostgreSQL syntax was added but not executed against a PostgreSQL instance.
- No production database, real `.env`, service restart, deployment, Provider,
  paid call, or production migration was used.
- The ProductVersion DELETE test uses an unreferenced historical version, so a
  foreign-key rejection cannot mask the trigger assertion.

## Synchronization

The exact three-file package was promoted only after testing-branch
verification to the actual production worktree:
`C:\Users\Reel\Documents\libtv-auto-main-sync` (`main`).

Main was independently checked with the same scoped Ruff and new migration
test after synchronization:

```text
.venv/Scripts/python.exe -m ruff check backend/alembic/versions/d2f3a4b5c607_creative_integrity_repair.py backend/tests/test_creative_migration_repair.py
.venv/Scripts/python.exe -m pytest backend/tests/test_creative_migration_repair.py -q
```

Result: `Ruff PASS`; `3 passed`, exit code 0.

Only the migration, new test, and this report were synchronized. No `.env`,
cache, runtime state, evidence directory, build artifact, or unrelated
production change was synchronized.
