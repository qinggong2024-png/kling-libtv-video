# Sprint Report: Creative Workflow CW-4A

Date: 2026-10-11

## Scope

Connect the approved `creative.text_contract` pure gate to the existing offline
Creative Workflow runtime with the smallest D4/E1 loop.

## Completed

- D4 (`select_direction` and revision `compile_package`) now freezes the complete
  plan, package, facts snapshot, and Prompt Registry snapshot with
  `freeze_text_contract`.
- The frozen contract is persisted in the task snapshot and as an append-only
  `CreativeRecord` with kind `text_contract`.
- The Registry snapshot now includes the literal Prompt and a deterministic
  rules manifest, while the task facts snapshot includes the canonical source
  SHA.
- E1 validates `plan`, actual package, frozen package, Registry snapshot, and
  facts snapshot with `validate_text_contract` before generation/revision costs,
  attempts, or outputs are created.
- Any rejected or unverified contract blocks execution with
  `TEXT_CONTRACT_REJECTED`; the gate never rewrites the Prompt.
- Revision packages receive a new D4 frozen contract before their E1 execution
  gate.

## Files

Modified or added within the CW-4A write boundary:

- `backend/src/libtv_agent/services/creative_workflow.py`
- `backend/src/libtv_agent/creative/workflow.py`
- `backend/tests/test_creative_workflow_text_contract_integration.py`
- `docs/SPRINT_REPORT_CREATIVE_WORKFLOW_CW4A_20261011.md`

Not changed by this package:

- migrations
- ORM schema
- OpenAPI
- frontend
- coordination tables
- `docs/CHANGELOG.md`

## Testing

Testing branch (`E:\Projects\libtv自动化生成`, `codex/testing`):

```text
.venv/Scripts/python.exe -m ruff check backend/src/libtv_agent/services/creative_workflow.py backend/src/libtv_agent/creative/workflow.py backend/src/libtv_agent/creative/text_contract.py backend/tests/test_creative_workflow_text_contract_integration.py
```

Result: PASS.

```text
.venv/Scripts/python.exe scripts/run_creative_targeted_tests.py --root E:\Projects\libtv自动化生成 --evidence-dir E:\Codex\cw4a-testing --tests backend/tests/test_creative_workflow_text_contract_integration.py backend/tests/test_creative_workflow.py backend/tests/test_creative_workflow_accounting.py backend/tests/test_creative_text_contract.py
```

Result: `75 passed`, exit code `0`.

The integration tests cover:

- D4 snapshot and append-only record persistence;
- E1 `generate` and `revise` positive paths;
- Prompt, facts, locks, Registry, and Reality tampering;
- blocking without candidate/cost side effects and without Prompt repair.

Actual production worktree (`C:\Users\Reel\Documents\libtv-auto-main-sync`,
`main`) after scoped synchronization:

```text
.venv/Scripts/python.exe -m ruff check backend/src/libtv_agent/services/creative_workflow.py backend/src/libtv_agent/creative/workflow.py backend/src/libtv_agent/creative/text_contract.py backend/tests/test_creative_workflow_text_contract_integration.py
```

Result: PASS.

```text
.venv/Scripts/python.exe scripts/run_creative_targeted_tests.py --root C:\Users\Reel\Documents\libtv-auto-main-sync --evidence-dir E:\Codex\cw4a-main --tests backend/tests/test_creative_workflow_text_contract_integration.py backend/tests/test_creative_workflow.py backend/tests/test_creative_workflow_accounting.py backend/tests/test_creative_text_contract.py
```

Result: `75 passed`, exit code `0`.

The targeted runner denied network connections and used isolated SQLite,
local object storage, fake adapters, and paid generation disabled.

## Hashes

SHA-256 after final report creation and synchronization:

- `backend/src/libtv_agent/services/creative_workflow.py`:
  `9B139E87BA82999F0B68634953110AC4F06966D9A1B3E1EBC60AE96A3AFDC1C8`
- `backend/src/libtv_agent/creative/workflow.py`:
  `2DCCF0E8A4A0EFFC227F41DAC29B4614D9965F25AEBD306ADD903F56756173FC`
- `backend/tests/test_creative_workflow_text_contract_integration.py`:
  `5FDCA5B758C220598C53EC2F87EC2754EE83BE0321DE5518A4E595D9FEB7CE98`

The report file hash is reported in the completion message after synchronization
to avoid embedding a self-referential hash in the report.

## Findings and limits

- This proves the offline SQLite/Fake runtime gate and existing Creative
  Workflow regressions only.
- PostgreSQL behavior, concurrent multi-worker transaction boundaries, and
  production data migration were not tested.
- No real Provider, paid generation, service restart, deployment, or production
  database was used.
- The text contract still does not prove real pixels, photographic causality,
  semantic revision safety, or actual image quality/realism gains.

## Synchronization

After testing verification, the three implementation/test files were copied
incrementally to the actual `main` worktree. The main worktree retained its
pre-existing unrelated changes. The report is synchronized separately after
the final hashes are recorded.

