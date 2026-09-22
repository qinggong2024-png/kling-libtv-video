# Fashion Video Factory V1 — Repository Baseline

Baseline date: 2026-08-13  
Pilot contract: `FASHION-VIDEO-FACTORY-V1-CODEX-MASTER-20260813`  
Branch inspected: `codex/testing`

## Verified repository facts

- Backend: Python 3.11, FastAPI, Pydantic, SQLAlchemy/Alembic, pytest.
- Frontend: React, TypeScript, Vite, Vitest.
- Existing batch-generation boundary: `fixed_video_tasks.py` plus the provider adapters.
- Existing provider adapters: LibTV, Kling API/CLI, WaveSpeed, and Bach.
- Existing reliability primitives: persisted task/attempt models, compare-and-swap state
  transitions, API idempotency records, concurrency controls, cost/points accounting,
  recovery services, retention, and observability.
- Existing deterministic media dependency: FFmpeg/ffprobe.
- Existing contract location: `backend/contracts/`; existing strong types are Pydantic models.
- Existing tests cover provider adapters, task workflow, state, idempotency, recovery,
  configuration, and observability.

## Missing capabilities required by the pilot contract

- No existing Cutflow implementation was found under that name or an equivalent complete
  `ShotPool -> semantic scheduler -> RenderPlan` pipeline.
- No structured temporal-error taxonomy, safe-salvage policy, qualified segment pool,
  beat-aware micro-alignment, BGM commercial-license gate, or independent pilot ground
  truth harness was found.
- No immutable `ProductTruthSnapshot` contract or final-video lineage contract matching
  the pilot contract was found.

## Reuse map

| Pilot boundary | Repository mapping | Decision |
| --- | --- | --- |
| Existing Batch Generator | `services/fixed_video_tasks.py`, provider adapters | Reuse through an adapter; do not rewrite |
| Queue/concurrency | runner, capacity and runtime-control services | Reuse |
| State/idempotency/resume | models, `state_machine.py`, `idempotency.py`, restore services | Reuse; add factory-level pure policy/state contract |
| Cost logging | points/billing/observability models and services | Reuse; pilot harness accepts actual cost records |
| Cutflow | No complete equivalent found | Add a lightweight, provider-independent module |
| Product/Temporal/Final QA | Partial technical validation only | Add structured policy contracts; keep automated QA separate from human ground truth |
| Product-to-model/VTON | Provider capability exists only in fragments | Defer until Phase 1 reliability path is validated |

## Integration constraints

- All factory behavior is disabled by default behind feature flags.
- Paid generation remains disabled; this implementation does not submit provider work.
- Existing task and production behavior must remain unchanged while the factory flag is off.
- The untracked historical contract-package files present before this work are user-owned and
  are intentionally untouched.

