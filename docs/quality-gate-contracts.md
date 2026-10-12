# Quality Gate Contracts

Window 6 adds a contract layer for future quality observations. It is
intentionally evidence-only and is not a second task state machine.

## Artifacts

- `backend/contracts/quality/image-quality-contract.schema.json`
- `backend/contracts/quality/video-quality-contract.schema.json`
- `backend/contracts/quality/review.schema.json`
- `backend/contracts/quality/failure-taxonomy.schema.json`
- `backend/src/libtv_agent/quality/`

The Pydantic models mirror the JSON Schemas and provide a narrow adapter
interface for normalizing observations. They do not change the existing API
contract, `frontend/src/api.ts`, backend routes, provider adapters, billing,
quota, ledger, task state, or production workflow.

## Semantics

`ImageQualityContract` and `VideoQualityContract` contain observations,
expected values, evidence, and optional failure codes. `QualityReview` is a
recommendation record with references to evidence. `PASS`, `WARNING`,
`QUALITY_REVIEW`, and `UNRESOLVED` are review recommendations only; existing
workflow and validation statuses remain authoritative.

`OFFLINE_SYNTHETIC_ONLY` is an explicit observation mode. It identifies
synthetic/replay evidence and does not authorize live provider calls, paid
submission, automatic review approval, or production blocking.

## Failure taxonomy

Failure codes classify evidence for reporting and later review. Taxonomy
entries carry family, severity, retryability, and whether a human review may
be needed. These flags are descriptive metadata; consumers must continue to
use the existing review and task-state semantics.
