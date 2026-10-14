# Sprint Report: PostgreSQL Acceptance Gap Closure

Date: 2026-10-14.
Verdict: **Backend READY for the requested PostgreSQL acceptance gate and controlled real-sample testing.**

This verdict is scoped to the three repaired blockers and the acceptance suite below. It is not production deployment, launch approval, or authorization for paid Provider generation.

## Completion

- Repaired the phase-width migration failure without editing historical migrations.
- Replaced PostgreSQL-incompatible JSON DISTINCT with an active-item EXISTS filter.
- Closed the budget-commit window with a final source qualification, lineage, and frozen-package check immediately before Provider submission.
- Validated codex/testing, promoted only these source changes to actual main, and independently validated main.
- No UI, Creative State, Workflow architecture, Provider capability, real credentials, production database, or online service changes.

## Changed Files

1. `backend/alembic/versions/ca01b2c3d405_parent_phase_capacity.py`: new registered migration widens `parent_task.phase` from VARCHAR(21) to VARCHAR(32).
2. `backend/alembic/versions/ca01b2c3d406_merge_phase_capacity.py`: merges the capacity-repair branch with the existing schema head.
3. `backend/alembic/env.py`: orders the new capacity step before the historical approval update during an upgrade that contains both; supports Alembic's supplied connection for isolated schema tests.
4. `backend/src/libtv_agent/services/image_generations.py`: selects active batches using correlated EXISTS.
5. `backend/src/libtv_agent/runner/supervisor.py`: performs the final source fence after the budget commit; releases claimed budget when this fence proves that no submission occurred.
6. `backend/tests/test_postgres_acceptance_repair.py`: three migration-plan regressions.
7. `backend/tests/test_postgres_production_acceptance.py`: migrated PostgreSQL acceptance fixtures and regressions, with external network connections prohibited.
8. `docs/SPRINT_REPORT_POSTGRES_GAP_CLOSURE_20261014.md`: this report.

Main's existing budget integration had an additional claim at the initial worker entry, before the normal submission-boundary claim. Its duplicate claim failed before localization or Provider submission. Scoped promotion removed only that premature duplicate; the durable claim immediately before submission remains. Other main-specific implementation differences were preserved.

The synthetic price fixture includes `all_parameters_upper_bound` only when the loaded pricing schema supports it. Existing pricing validation still executes; no budget or Provider authorization checks are bypassed in business code.

## Migration

The old approval migration writes the 22-character `AWAITING_FINAL_APPROVAL` into a field created with width 21. A migration appended only after that failing step cannot repair a fresh upgrade. The new repair is therefore a branch from its prerequisite, plus a merge at head. Alembic's environment moves only this registered capacity step before the historical approval step when both are present in the upgrade plan.

All historical steps still run normally and are recorded by Alembic. No stamping, metadata initialization, direct database repair, or historical migration edits were used. The existing migration graph has multiple merges; relying only on sibling-branch traversal order did not ensure the required ordering.

- Testing CLI `alembic -c backend/alembic.ini upgrade head`: PASS from the empty public schema.
- Actual main CLI `upgrade head`: PASS, already at the shared isolated database head.
- Both suites independently replay the full migration history into a fresh unique schema for every database test.
- Final head: `ca01b2c3d406`.
- SQL inspection: `parent_task.phase` is `character varying(32)`.
- Schema readiness: ready, matching current/expected revision, no missing tables.
- Actual `/health/ready` handler via ASGI: HTTP 200 on both worktrees; PostgreSQL and databaseSchema checks both `ok`.
- No residual acceptance/test schemas remain.

Capacity downgrade deliberately retains VARCHAR(32), because narrowing could truncate approval states. Merge downgrade and the remaining historical downgrade machinery are unchanged. Upgrading Alembic itself should rerun the migration-plan and fresh-database regressions because the repair depends on its step execution contract.

Historical migration SHA256 values remain unchanged:

- `a6c8e2f4b901_business_quality_gates.py`: `5D69C1D152A8F1CFF2759FE85FB94E43323F40C92A2FC2BE6F6917EE75651F4A`.
- `f59dc2804e6f_phase_one_core_schema.py`: `A733E52C592B4800675625A618D6B4671D34F65AA69D8E056B72B5171F6864AE`.

## Data Flow And Race Repair

The existing request, preparation, Provider executor, output persistence, review, and delivery paths remain in use.

Video submission now follows:

`validate source -> durable budget claim/commit -> fresh source/package validation -> Provider submit -> existing persistence`

The final validation reloads source state, verifies ownership and QUALIFIED, checks stored source hashes against variant lineage, and verifies the frozen Package binding. Existing source-output row locks remain held through the immediate submission call. There is no intervening commit between the final Kling source fence and Provider submit. LibTV command-host and in-process generation also receive the final check at their submission boundary.

If validation fails after budget claiming:

- Provider call count is zero.
- Attempt becomes the existing `FAILED_BEFORE_SUBMIT`; command becomes `TERMINAL`.
- Existing aggregation handles parent/variant state; no new state machine is introduced.
- Task reason and `VIDEO_SOURCE_BLOCKED` audit record identify the failure.
- The claimed AI budget is `RELEASED` with `NOT_SUBMITTED`; existing points handling is retained.

Tested reasons: `SOURCE_IMAGE_NOT_QUALIFIED`, `SOURCE_IMAGE_CHANGED`, and `CREATIVE_WORKFLOW_BLOCKED`.

Active batch recovery now selects each batch once when at least one active item has a Provider task ID. Existing Provider exclusions, creation order, and batch-count limit remain. JSON values are no longer compared by DISTINCT.

## Tests

PostgreSQL 17.6: `127.0.0.1:15439/g1_safety`, role `g1_acceptance`, loopback only, `read committed`.

| Validation | codex/testing | Actual main |
| --- | --- | --- |
| Alembic upgrade / schema readiness | PASS | PASS |
| `/health/ready` | 200 | 200 |
| Migration plan regressions | 3 passed | 3 passed |
| Create / worker / submit qualification boundaries | 3 passed | 3 passed |
| Analysis retry, Package lineage/ownership, review/delivery | 4 passed | 4 passed |
| Stale/owner/expired claims, launch/cancel races | 8 passed | 8 passed |
| Two workers, one/two commands, no duplicate submission | 2 passed | 2 passed |
| Qualification revoked during materialization | 1 passed | 1 passed |
| Post-budget-commit qualification/lineage/Package revocation | 3 passed | 3 passed |
| Active image recovery and uniqueness/limit semantics | 2 passed | 2 passed |
| Total | **26 passed, 0 failed, 0 skipped** | **26 passed, 0 failed, 0 skipped** |
| Scoped Ruff / diff whitespace checks | PASS | PASS |

Testing duration: 49.106 seconds. Main duration: 46.993 seconds. Three migration-plan cases do not access a database; all remaining 23 cases use fresh Alembic-migrated PostgreSQL schemas. SQLite was not used as acceptance evidence.

Command used in both worktrees, with `G1_TEST_POSTGRES_URL` and `DATABASE_URL` set to the isolated endpoint:

```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_postgres_acceptance_repair.py backend/tests/test_postgres_production_acceptance.py --tb=short --show-capture=no
```

Workers use independent database sessions and real PostgreSQL transaction/claim behavior. Media, price entries, and Provider executors are synthetic; external network connections are blocked except for the isolated PostgreSQL endpoint and Windows internal socket pairs.

## Evidence And Promotion

Evidence root:

`E:/Codex/visualizations/2026/10/14/01a13875-5f79-7ac0-ad9a-a985d5dd16d5/postgres-acceptance`

- `gap-migration-testing.log`: fresh public-schema upgrade, including capacity repair before the historical approval update.
- `gap-closure/full-testing.xml`, `gap-closure/full-main.xml`: final acceptance results.
- `gap-closure/readiness-testing.json`, `gap-closure/readiness-main.json`: PostgreSQL identity, schema readiness, HTTP response, and empty residual-schema list.

Actual main location: `C:/Users/Reel/Documents/libtv-auto-main-sync`.

The two new migrations, Alembic environment, two new test files, and this report are synchronized. Business files received only the scoped fixes and main's necessary duplicate-budget-claim reconciliation; unrelated dirty changes were retained. No runtime evidence, database files, caches, secrets, or real `.env` were copied. Source synchronization succeeded; it is not a live deployment or production migration.

## Remaining Production Risks And Next Steps

- These tests cover concurrent asynchronous workers in one process, not multi-host workers, process-kill recovery, or long-running load.
- Real Provider transport, supplier quality, billing reconciliation, production object storage, and real media decoding were not exercised by this synthetic acceptance.
- Production database upgrade, online readiness, deployment, and backup/rollback rehearsal remain separate work.
- Existing accounting implementation differs between the two dirty worktrees; this suite verifies budget release at the repaired pre-submit block and does not certify complete real-provider accounting.
- Parallel unrelated work remains in both worktrees. Results certify the source loaded during these runs, not an immutable release commit.

The three requested PostgreSQL blockers are closed. A controlled real-sample test may proceed after the owner supplies its sample and approves its Provider/budget boundary. This task itself made no paid calls and grants no deployment or launch approval.
