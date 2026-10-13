# Sprint Report: Creative Workflow CW-3D

Date: 2026-10-10
Scope: isolated Alembic migration verification and a narrow targeted test runner

## Completed

- Added an explicit-file targeted pytest runner with `--root` and `--tests`.
- Kept runner cwd, pytest basetemp, JUnit XML, SQLite, and generated network guard outside the repository.
- Added a data-bearing migration test from `d0c1e2f3a405` to `d1e2f3a4b506`.
- Verified old ProductVersion and Creative Workflow rows by count and fact hash, `USER_UPLOAD` with a null URL, unique request-key enforcement, immutable history updates/deletes, and the existing downgrade refusal.

The socket guard only protects this test process; it is not an operating-system sandbox. Tests use ASGITransport and file SQLite and do not need loopback access.

## Files

Only these files belong to CW-3D:

- `backend/tests/test_creative_migration_integrity.py`
- `scripts/run_creative_targeted_tests.py`
- this report

No migration, model, schema, API, shared conftest, OpenAPI, old harness, or business source file was changed.

## Testing

The runner prints the root, source hash, exact command, exit code, external JUnit path, and pytest counts. The test package keeps strict failures for missing DELETE triggers instead of changing an earlier migration or hiding the failure.

Testing result on 2026-10-10: one preservation/upload test passed. Two strict integrity assertions failed because `creative_command` DELETE and `product_version` DELETE were accepted by SQLite after the CW-2 migration. The downgrade refusal check passed after the test assertion was corrected to count both retained versions. These are migration findings for the PM, not fixes made in CW-3D.

Testing command:

```text
.venv/Scripts/python.exe -m ruff check backend/tests/test_creative_migration_integrity.py scripts/run_creative_targeted_tests.py
.venv/Scripts/python.exe scripts/run_creative_targeted_tests.py --root E:\Projects\libtv自动化生成 --evidence-dir F:\Temp\cw3d-testing-evidence-final3 --tests backend/tests/test_creative_migration_integrity.py
```

Testing result: Ruff PASS; pytest `2 passed, 2 failed`, exit code 1. Evidence: `F:\Temp\cw3d-testing-evidence-final3\junit.xml`. Testing source hash printed by the runner: `ed0bf94233e074cdb7cc297401832dd25ba98cc4d4ba38fad4d8851433bd0dff`.

Actual main command:

```text
.venv/Scripts/python.exe -m ruff check backend/tests/test_creative_migration_integrity.py scripts/run_creative_targeted_tests.py
.venv/Scripts/python.exe scripts/run_creative_targeted_tests.py --root C:\Users\Reel\Documents\libtv-auto-main-sync --evidence-dir F:\Temp\cw3d-main-evidence-final --tests backend/tests/test_creative_migration_integrity.py
```

Actual main result: Ruff PASS; pytest `2 passed, 2 failed`, exit code 1. Evidence: `F:\Temp\cw3d-main-evidence-final\junit.xml`. Main source hash printed by the runner: `d79667a70571d9a412f50556440b7e129264331a487bebc8decf2f37d5890920`.

## Findings and limits

- `Base.metadata.create_all` is not used as migration evidence.
- PostgreSQL, cross-process races, crash recovery, and production data were not tested.
- No real `.env` was read, no service was started, and no Provider or paid call was made.
- Existing application tests using `create_all` do not prove database triggers or PostgreSQL concurrency.

## Synchronization

The exact three-file promotion succeeded by file copy to the actual main directory. New-file hashes match on both sides:

- `backend/tests/test_creative_migration_integrity.py`: `27B607E7A090E63120307CA15790FE3C5B8B5F0BCEF15F51146452AD4EB0BCF2`
- `scripts/run_creative_targeted_tests.py`: `DF04B2BBE024ABE8B5AA8472C1E301B3C9A64CBA634C2A56C854B35CC323FD73`
- `docs/SPRINT_REPORT_CREATIVE_WORKFLOW_CW3D_20261010.md`: `05235B04E0E93E60F34DCAC51EDB438091D9E7D75776EAB7AC4B0FF2555F5FBD`

Migration baseline hashes match on both sides:

- `d0c1e2f3a405_creative_offline_foundation.py`: `D2190BF257A9C3CDAD7AE58974CA34DD19A8B05DCDB2F349123EE09EDC15E035`
- `d1e2f3a4b506_creative_isolated_integrity.py`: `D7F2D97EDD55F9F0A7FD0417DE8141CF14A454AE20788ED820F5418CC5F77631`

PG, cross-process concurrency, crash recovery, real Provider, service startup, production migration, and frontend checks remain unverified. The two strict SQLite trigger failures must be handled by a later migration repair window; CW-3D did not modify either historical migration.
