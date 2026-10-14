# Sprint Report: PostgreSQL Production Acceptance

Date: 2026-10-14. Verdict: **Backend Final NOT READY**.

## Completion

- Started a new disposable PostgreSQL 17.6 cluster at `127.0.0.1:15439/g1_safety`.
- Confirmed the server version, database, listening address, port, and `read committed` isolation through SQL.
- Ran existing Alembic `upgrade head` on both current worktrees. Both failed.
- Ran schema inspection and the actual `/health/ready` handler against the isolated database.
- Ran PostgreSQL-only claim tests, two-worker scheduler diagnostics, and qualification revocation diagnostics on both worktrees.
- No SQLite tests, real Provider calls, paid generation, UI validation, production database writes, production migrations, or production restarts.

## Changes

Only this report is a repository change for this task. No business logic, state machine, Workflow, Provider, or migration source was changed.

The test harness and all database files are outside the repository:

`E:/Codex/visualizations/2026/10/14/01a13875-5f79-7ac0-ad9a-a985d5dd16d5/postgres-acceptance`

This directory contains `pgdata`, `postgres.log`, `test_postgres_acceptance.py`, `check_readiness.py`, migration logs, readiness JSON, and JUnit results. PostgreSQL binaries were reused from the historical isolated G1 evidence directory; the historical data directory was not reused.

The new cluster listens only on loopback and uses a disposable local role, `g1_acceptance`, with local trust authentication. It is not production configuration. It remains running for diagnosis. Runtime state must not be promoted to main.

## Tests

| Check | codex/testing | Actual main |
| --- | --- | --- |
| PostgreSQL connection | PASS | PASS |
| Alembic upgrade head | FAIL | FAIL |
| Schema readiness / HTTP readiness | NOT READY / 503 | NOT READY / 503 |
| Claim fence, recovery/launch/cancel races | 8 passed | 8 passed |
| Qualification: create, worker execution, pre-submit materialization | 3 passed | 3 passed |
| Two workers: one command claimed/submitted once | 1 passed | 1 passed |
| Two workers: two overlapping submissions, one per command | 1 passed | 1 passed |
| Qualification revoked during materialization in a separate session | 1 passed | 1 passed |
| Qualification revoked after budget claim commit, before Provider submit | FAIL: fake Provider called once | SKIPPED: this worktree lacks `_claim_video_budget` |
| Active image recovery query | FAIL: JSON equality operator unavailable | FAIL: JSON equality operator unavailable |

Totals for the final diagnostic sets: testing **14 passed, 2 failed**; main **14 passed, 1 failed, 1 skipped**. Migration failure is separate from pytest totals. The skipped main case is not a pass.

Claim tests explicitly selected `-k postgresql`; 8 SQLite cases were deselected, not run. The external harness asserts the exact endpoint and PostgreSQL dialect, initializes unique schemas with `Base.metadata.create_all()`, and drops those schemas afterward. Fake executors, synthetic image pixels, and configured synthetic prices are used. External network connections are blocked by the harness; Windows internal socket pairs are permitted.

These are real PostgreSQL transaction diagnostics on model-created schemas. They do **not** demonstrate successful migration or execution on a migrated production-compatible schema. Workers are concurrent asynchronous supervisors with independent database sessions in one process; this is not a multi-host or process-kill acceptance.

Final evidence:

- `claim-testing.xml`, `claim-main.xml`: 8 passes each.
- `boundaries-testing.xml`, `boundaries-main.xml`: 6 passes each.
- `blockers-testing.xml`: 2 failures.
- `blockers-main.xml`: 1 failure and 1 explicitly inapplicable skipped case.
- `migration-testing.log`, `migration-main.log`: PostgreSQL migration failures.
- `readiness-testing.json`, `readiness-main.json`: schema false, HTTP 503, empty public schema after transactional rollback.
- `races-testing.xml` is an intermediate harness run, not a final acceptance result. Its worker-distribution expectation was overly strict; the final harness tests distinct worker overlap and duplicate prevention explicitly.

Both worktrees were already dirty, and unrelated parallel source work continued during acceptance. Results certify the source loaded by those individual runs, not an immutable release candidate or completed synchronization of other tasks.

## Blocking Findings

1. **PostgreSQL migration cannot reach head.** Migration `f59dc2804e6f` creates non-native enum `parent_task.phase` with width 21. Migration `a6c8e2f4b901`, line 74, attempts to write the 22-character `AWAITING_FINAL_APPROVAL` without first extending that column. PostgreSQL raises `StringDataRightTruncationError`, including on a fresh empty database. Both worktrees reproduce the error. The complete migration transaction rolls back: no public application tables or current Alembic revision remain. Expected head is `c9f0a1b2c3d4`; readiness correctly returns 503.

2. **PostgreSQL active image recovery query fails.** `services/image_generations.py::refresh_active_batches` selects the full batch with `DISTINCT`, including `request_json` and `error_json` mapped as PostgreSQL `json`. PostgreSQL cannot compare this type for DISTINCT and raises `UndefinedFunctionError`. The startup helper catches and logs the exception, which lets other tests pass while automatic image recovery remains broken. Direct diagnostic invocation fails on both worktrees.

3. **Qualification revocation can cross the budget-commit window on testing.** `_execute_kling` checks video inputs, then `_claim_video_budget` calls `claim_media_submission`, which commits and releases the source output row lock. A separate request can commit `REJECTED` before the subsequent adapter submit. The diagnostic calls the original budget claim, then performs and awaits a real qualification-revocation API request, and then returns to the unchanged worker. The fake Provider receives one request. This is a transaction-ordering failure, not a real paid call. Main lacked this budget-commit method when inspected, so the corresponding main diagnostic is explicitly inapplicable and cannot certify promotion of the new boundary.

## SQLite Differences

No SQLite execution was performed in this task.

- PostgreSQL enforces VARCHAR width; SQLite's usual VARCHAR affinity does not establish equivalent length enforcement. This explains why SQLite-only migration evidence cannot certify this upgrade.
- PostgreSQL `json` lacks the equality operator needed by the current DISTINCT query. SQLite uses a different JSON representation and query semantics.
- PostgreSQL row locks and `SKIP LOCKED` were exercised by independent sessions. Capacity ownership, durable command/attempt handoff, no duplicate submission, and capacity release were asserted.
- The last-budget-commit qualification gap was reproduced on PostgreSQL. It is not established as PostgreSQL-only; committing releases the protection regardless of the earlier validation success.

## Next Steps

Backend Final remains **NOT READY**, and the requested gate does not permit real sample testing.

A separately authorized repair should address the three observed blockers with minimal changes, then repeat `upgrade head`, readiness, and the complete PostgreSQL suite on a stable, synchronized release candidate. Do not stamp the database, alter it manually to bypass the migration failure, substitute SQLite, or reinterpret metadata-created schemas as migration acceptance.

Only this report is synchronized to actual main for this task. Existing business changes, credentials, runtime files, test database files, caches, and generated evidence are not promoted.
