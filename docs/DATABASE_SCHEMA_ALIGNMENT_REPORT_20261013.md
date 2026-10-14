# Database Schema Alignment Report

Date: 2026-10-13

## 1. Environment

```makefile
branch: codex/testing
commit: d6de53f6293f1a7466de02543ae8dd2fab8cb257
path: E:\Projects\libtv自动化生成
worktree_status: dirty_before_this_report
app_env: development
```

The worktree already contained unrelated uncommitted source and documentation changes. This task did not modify or revert them.

## 2. Current Database

```yaml
Current Database: E:\Projects\libtv自动化生成\var\development.db
Environment: local development SQLite
Backup Required: yes
Migration Path: c9f0a1b2c304 -> d0c1e2f3a405 -> d1e2f3a4b506 -> d2f3a4b5c607 -> e4f5a6b7c809 -> e5f6a7b8c901
```

Evidence:

- `.env` contains `APP_ENV=development`.
- `.env` contains `DATABASE_URL=sqlite+aiosqlite:///var/development.db`.
- The resolved database file is approximately 20 MB.
- Alembic reports `SQLiteImpl`.
- No migration, backup, configuration change, or database write was performed.

## 3. Schema Status

```makefile
current_revision: c9f0a1b2c304
head_revision: e5f6a7b8c901
alignment: not aligned
```

The database currently lacks all five schema objects required by the readiness check:

```makefile
creative_task: missing
creative_record: missing
creative_command: missing
creative_creation: missing
creative_prompt_registry: missing
```

## 4. Runtime API

### Live health

```makefile
endpoint: http://127.0.0.1:8000/api/v1/health/live
status: 200
response: {"status":"ok"}
```

### Ready health

```makefile
endpoint: http://127.0.0.1:8000/api/v1/health/ready
status: 503
response: degraded; postgresql=ok; databaseSchema=outdated
```

The readiness response reports:

```json
{
  "currentRevisions": ["c9f0a1b2c304"],
  "expectedRevisions": ["e5f6a7b8c901"],
  "missingTables": [
    "creative_command",
    "creative_creation",
    "creative_prompt_registry",
    "creative_record",
    "creative_task"
  ]
}
```

The system status endpoint also reports `environment=development` and `schemaRevision=c9f0a1b2c304`.

## 5. Migration Plan

The migration graph is linear from the current revision to the head:

```text
c9f0a1b2c304
  -> d0c1e2f3a405
  -> d1e2f3a4b506
  -> d2f3a4b5c607
  -> e4f5a6b7c809
  -> e5f6a7b8c901
```

### `d0c1e2f3a405`

- Creates `creative_task`.
- Creates `creative_record`.
- Creates `creative_command`.
- Adds foreign keys to the existing `app_user`, `product`, and `creative_task` tables.
- Adds indexes and uniqueness constraints.

### `d1e2f3a4b506`

- Makes `product_version.product_page_url` nullable.
- Adds `source_type` with the default `PRODUCT_PAGE`.
- Adds nullable `request_key` and `request_hash`.
- Adds the `(product_id, request_key)` uniqueness constraint.
- Creates `creative_creation`.
- Creates `creative_prompt_registry`.
- Adds SQLite immutability triggers for creative history and product facts.
- Uses SQLite batch table alteration for `product_version`.

### `d2f3a4b5c607`

- Adds immutability triggers for product facts and creative commands.
- Does not create or delete application data.

### `e4f5a6b7c809`

- Creates `provider_submission_ticket`.
- Adds indexes and uniqueness constraints.
- The table intentionally has no foreign keys to generation attempts, quota reservations, points ledgers, or provider tasks.

### `e5f6a7b8c901`

- Creates `provider_input_lease`.
- Adds indexes and uniqueness constraints.

## 6. Conflict, Dependency, and Data Safety Analysis

```makefile
revision_conflict: none detected
multiple_heads: no
upgrade_drop_tables: none in the requested path
upgrade_drop_columns: none in the requested path
old_table_dependencies: app_user, product, product_version, creative_task
field_initialization: source_type defaults to PRODUCT_PAGE; request_key and request_hash are nullable
sqlite_batch_alteration: yes, in d1e2f3a4b506
```

The upgrade path is linear and its upgrade functions add tables, columns, indexes, constraints, and triggers. It does not explicitly delete existing rows or drop existing tables. The SQLite batch alteration rewrites `product_version`, so an external backup is required before execution.

Downgrades are destructive: they drop the newly created tables and remove the added columns and constraints. The `d1e2f3a4b506` downgrade also refuses to continue if an upload version has a null product URL.

## 7. Blocking Issues

```text
P0:
- Local development database is behind the application migration head.
- /api/v1/health/ready returns 503.
- Required creative tables are absent.

P1:
- No verified database backup exists for this alignment operation.
- SQLite batch alteration requires extra recovery care.

P2:
- After schema alignment, the full browser-to-API workflow still requires a separate smoke validation.
```

## 8. Recommended Fix Order

1. Confirm that `E:\Projects\libtv自动化生成\var\development.db` is disposable or approved as the local development database.
2. Create a timestamped backup of that SQLite file.
3. Run:

   ```powershell
   uv run alembic -c backend/alembic.ini upgrade head
   ```

4. Verify Alembic reports `e5f6a7b8c901`.
5. Verify the five required creative tables exist.
6. Verify `/api/v1/health/live` returns `200`.
7. Verify `/api/v1/health/ready` returns `200`.
8. Re-run the browser and API runtime smoke checks before starting any real product test.

## 9. Execution Status

Migration execution is **pending explicit confirmation**. This report was produced without modifying application code, API contracts, workflows, adapters, providers, environment variables, or database contents.
