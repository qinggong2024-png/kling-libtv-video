# CRB-2 Reliability Sprint Report

Date: 2026-10-13 (Asia/Shanghai)
Window: independent B, evidence-only closeout
Source HEAD: 2385587 (detached worktree from codex/testing)

## Completion

- Reviewed the required project documents and CRB-2 implementation review.
- Read `SPRINT_REPORT_CRB2_RECOVERY_20261013.md` directly from the primary
  testing workspace because it is absent from this worktree. Its historical
  33-test result is not counted as a result of this run.
- Ran the existing minimum SQLite/Fake suite: 29 passed, 1 deselected.
- Distinguished unique ticket INSERT from an execution-stage claim. No claim
  of Provider at-most-once, PostgreSQL reliability, or hard-crash recovery.
- Closed as a report per PM's latest scope instruction. No new tests or
  service changes; unresolved business behavior is handed to PM.

## Changes And Isolation

Only deliverable:

```text
docs/SPRINT_REPORT_CRB2_RELIABILITY_20261013.md
```

No source snapshot was copied or committed. No primary testing workspace
writes, main synchronization, migrations, production data writes, Provider
calls, remote uploads, environment installs, or service starts/restarts.
Existing tests use synthetic images and isolated local object-store writes.
Temporary test artifacts remain outside the source worktree.

## Baseline Evidence

Independent workspace: `E:/Codex/worktrees/97b1/libtv自动化生成`.
Primary testing workspace: `E:/Projects/libtv自动化生成`, branch
`codex/testing`, HEAD `2385587` at intake, with unrelated dirty Creative State
and frontend files preserved.

Raw SHA-256 differs for some files because of checkout line endings:

| File | Independent SHA-256 | Primary testing SHA-256 |
| --- | --- | --- |
| `backend/src/libtv_agent/app.py` | `E8D9F0E8A99ED03B1D607F34DB3E921D7963664670D611B2EC3E19C462075A30` | `CEB8FE462A21F71C01A7E3C9E130BFFF57FCF244039737B88DE2422EC1DCA2B2` |
| `backend/src/libtv_agent/services/creative_provider_executor.py` | `10BFBE75B3C19D2A9EDE96D4FB45C4C953DAB5E16A4BFDAD93A6821616904710` | `8CA9265C3981BC0D2C464EB797A7D348E5C571F670B0258B80613ECDE70DB5AE` |
| `backend/src/libtv_agent/services/creative_provider_submission_persistence.py` | `78AE8F1B92DD50483D54A1C74917B0CC7F2FB683EB28020B27EBAF5F0FFBCCE4` | `0D99EB0BFA3CB8C7BDD60526F5B432B33C19E3DC2B09C748FD9EC554B183C74D` |
| `backend/tests/test_crb2_isolated_replay.py` | `CC4B12A799B518F9B1AA011ED7BFA423E5E0ACC1D455425BD85C023DAC333ED5` | `9ED447E8529AE9F8CF93FF8EB9324B73A6C99C732E311AC38CE089AF3D0AF029` |

The following comparison returned exit 0 for each of app, API router,
executor, submission persistence, Creative workflow, isolated replay test,
workflow recovery test, and submission persistence test:

```powershell
git diff --no-index --quiet --ignore-space-at-eol -- $t (Join-Path 'E:\Projects\libtv自动化生成' $t)
```

`backend/tests/conftest.py` SHA-256 is identical on both sides:
`AF6C1A2373A40474DD53634AC7167095492AA00F2E366C203985531AF0989F5F`.
`pyproject.toml` SHA-256 is identical on both sides:
`A32E5991ECA71E43C078E4B9ECFC8C4436D56E0FDBA9BA8FE11B90AC0B1D2F99`.
`api/router.py:43` includes products, `:44` includes Creative workflow,
and `app.py:559` includes that API router. Product creation succeeded during
the final run; no stale-worktree products 404 was treated as a defect.

## Tests

All commands ran from the independent workspace. Existing shared interpreter:
`E:/Codex/worktrees/crb2-isolated-replay/libtv自动化生成/.venv/Scripts/python.exe`.
`pyproject.toml` sets `pythonpath = ["backend/src"]`.

Final successful command, with a short, pre-created temporary parent:

```powershell
New-Item -ItemType Directory -Force -Path 'E:\Codex\crb2-b-tmp' | Out-Null
$env:TEMP='E:\Codex\crb2-b-tmp'
$env:TMP='E:\Codex\crb2-b-tmp'
$env:APP_ENV='test'
$env:DATABASE_URL='sqlite+aiosqlite:///:memory:'
$env:PYTHONDONTWRITEBYTECODE='1'
& 'E:\Codex\worktrees\crb2-isolated-replay\libtv自动化生成\.venv\Scripts\python.exe' -m pytest backend/tests/test_crb2_isolated_replay.py backend/tests/test_creative_workflow_recovery_contract.py backend/tests/test_creative_provider_submission_persistence.py backend/tests/test_creative_provider_executor.py backend/tests/test_submission_recovery.py -k 'not migration' -q -p no:cacheprovider --basetemp 'E:\Codex\crb2-b-tmp\p1' --tb=short -o addopts=''
```

Result: exit 0, `29 passed, 1 deselected in 31.72s`.
The migration test was deliberately excluded; no migration evidence is claimed.

| Test file | Passed | Actual evidence |
| --- | ---: | --- |
| `test_crb2_isolated_replay.py` | 3 | Synthetic mapping, command replay, source/package/ProductVersion rejection |
| `test_creative_workflow_recovery_contract.py` | 5 | UNKNOWN/WRITE_UNCERTAIN command blocking, explicit reconcile, stop, app/engine reconstruction |
| `test_creative_provider_submission_persistence.py` | 9 | Ticket persistence, terminal states, unique INSERT race between two SQLite sessions |
| `test_creative_provider_executor.py` | 7 | Existing offline controls, explicit test-double marker, ticket terminal/expiry rejection |
| `test_submission_recovery.py` | 5 | Owner-scoped/redacted lookup, ambiguity, authentication, no retry permission |

Ruff:

```powershell
& 'E:\Codex\worktrees\crb2-isolated-replay\libtv自动化生成\.venv\Scripts\python.exe' -m ruff check --no-cache backend/tests/test_crb2_isolated_replay.py backend/tests/test_creative_workflow_recovery_contract.py backend/tests/test_creative_provider_submission_persistence.py backend/tests/test_creative_provider_executor.py backend/tests/test_submission_recovery.py
```

Result: exit 0, `All checks passed!`.

Initial attempts used the same five files and `-k 'not migration' -q
-p no:cacheprovider`, with the following long `--basetemp` paths:

```text
E:\Codex\visualizations\2026\10\13\01a13325-3d86-7dc2-b14d-1e55922145c3\crb2-reliability-pytest
E:\Codex\visualizations\2026\10\13\01a13325-3d86-7dc2-b14d-1e55922145c3\crb2-reliability-pytest-rerun
```

First attempt exited 1 with `[WinError 5]` accessing the pytest temp directory.
The elevated retry exited 1 with 15 failed and 14 passed, failing during local
synthetic input copying with `FileNotFoundError` on deep object-store paths.
The identical suite passed after shortening paths and setting TEMP/TMP.
No test code was changed to address these environment failures. They do not
constitute deliberate CRB-2 output-write failure injection or acceptance.

Final whitespace/scope checks:

```powershell
git diff --check
git diff --no-index --check -- NUL docs/SPRINT_REPORT_CRB2_RELIABILITY_20261013.md
git status --short
```

The untracked report requires the no-index check; ordinary `git diff --check`
alone does not inspect its contents. Tracked diff check exited 0. Report
no-index check emitted no whitespace errors and exited 1 for the added-file
difference; Git emitted only an LF/CRLF conversion warning. Status contained
only this untracked report; no tracked source changes.

## Findings And Blockers

| Boundary | Status and concrete reason |
| --- | --- |
| PostgreSQL | Not proved. `Test-Path Env:G1_TEST_POSTGRES_URL` returned False; no isolated PostgreSQL target was supplied. The selected fixtures instantiate SQLite directly. No PostgreSQL connection or availability probe was attempted; this does not claim PostgreSQL is absent from the host. PM stopped environment exploration/installation. |
| Multi-worker claim | Only two independent SQLite sessions in one Python process were tested (`test_sqlite_unique_insert_makes_one_claim_winner`, line 225). No independent worker processes, PostgreSQL contention, or lock-wait harness was run. One `created` winner proves a unique registry INSERT, not one adapter execution. |
| Executor at-most-once | Not proved; source-level gap. `creative_provider_executor.py:343-349` reads ticket state via `get` and checks READY_TO_SUBMIT. No execution-stage atomic transition or ownership token is acquired before adapter calls at `:414-433`. `SubmissionClaim.created` is not an executor lock. |
| Claim committed / result missing | Source-level recovery gap, not a hard-crash experiment. `claim_submission` stores READY_TO_SUBMIT and returns INSERT rowcount (`creative_provider_submission_persistence.py:151-197`). After claim commit, termination before result persistence leaves that READY record with no result/remote task evidence. A new reader cannot distinguish unused permission from an external side effect whose receipt was lost. Result row locks at `:227-245` occur after execution and cannot prove pre-call exclusion. |
| Test-double success | `creative_provider_executor.py:501-508` returns TEST_DOUBLE before `record_provider_result` at `:509`. A passing fake adapter call is not proof of durable execution state advancement or prevention of another execution. No real submission was attempted. |
| Restart / hard crash | App/engine reconstruction passed in one process (`test_creative_workflow_recovery_contract.py:337`). No process was killed/restarted, no crash was injected after claim commit or external acceptance, and no lost-receipt recovery was exercised. Additionally, shared conftest uses SQLite journal_mode=MEMORY and synchronous=OFF; these fast tests do not establish crash durability. |
| UNKNOWN / WRITE_UNCERTAIN | Passed only for persisted Fake command snapshots: new generate/revise/authorize blocked; explicit reconcile_not_submitted permits resume. Generic submission lookup forbids retry. This does not prove Provider reconciliation, ticket-to-batch recovery, or real cost settlement. |
| Output write failure | Not proved. Selected tests have no controlled output object-store/DB-write failure after a returned generation result and no partial-output recovery assertion. Earlier input-copy environment failures are not this scenario. No new failure harness was added under the PM closeout instruction. |

The execution/recovery findings are handed off without changing production
services. No assertion that live currently submits duplicates is made: these
are missing guarantees/evidence, and existing live controls remain in place.

## Next Steps And PM Decisions

1. Decide whether to retain the current offline-only scope or authorize a
   separate execution-claim/recovery implementation package. Define durable
   execution ownership, pre-side-effect state, crash recovery, and no-handle
   reconciliation before claiming Provider at-most-once.
2. Supply an explicitly isolated PostgreSQL database/schema and approve a
   separate multi-process contention and hard-crash harness. Keep production
   databases and formal services outside that harness.
3. Authorize a focused output-write failure/recovery test package; define
   expected state and cleanup for object-store and database partial writes.
4. Keep billing source, UNKNOWN settlement, Provider/model, request-level
   authorization, and CRB-5 live approval as separate human decisions.
5. PM independently revalidates and promotes only approved files. This window
   intentionally did not inspect/modify main or synchronize production.

This report does not establish PRODUCTION_LOOP_READY, PRODUCTION_READY,
Checkpoint acceptance, deployment approval, or paid-generation approval.
