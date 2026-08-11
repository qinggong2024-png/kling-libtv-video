# Automatic Production Monitoring Gap Audit

Date: 2026-08-11  
Scope: `PREPARE_GUARDED_REAL_BATCH_PILOT` production enablement only

## Existing Monitoring

- `operations_snapshot` is exposed through the admin operations endpoint and SSE.
- Runtime configuration, queue/attempt state, points reservations, Runner heartbeats,
  orphan process samples, pipeline latency, throughput, and business baseline are
  already persisted or calculated from the database.
- Provider submission safety already blocks paid work for paused, unknown, and
  unreconciled states. Technical validation and final human approval are existing
  workflow gates.
- Asset SHA-256 provenance and cross-task reference checks are already available.

## Missing Pilot Monitoring

The previous surface did not present these controls in one machine-readable snapshot:

1. A named `humanReviewQueue` for product fidelity, human-critical, and final approval.
2. A `runtimeRevisions` object with an optional persisted Pilot lock and drift result.
3. The required `INFO`, `ACTION_REQUIRED`, and `CRITICAL` alert vocabulary.
4. Explicit `MEASUREMENT_GAP` output instead of null metrics without explanation.
5. Generation success and retry rates in the Pilot baseline.

## Keep / Adapt

- KEEP the existing operations endpoint, SSE stream, operational samples, runtime
  pause controls, provenance checks, technical QA, and human approval endpoints.
- ADAPT only `services/observability.py` and its regression tests to expose the five
  fields above and raise critical alerts for runtime drift, paid uncertainty, and
  cross-task asset contamination.
- No new monitoring platform, microservice, notification system, or Contract
  Manifest was introduced.

## Blocking Gaps

None in the local implementation after this adaptation. A non-empty
`runtimeRevisions.drift`, paid-state uncertainty, or cross-task asset contamination
is a runtime `CRITICAL` condition and automatically blocks the paid path through the
existing pause/reconciliation controls.

The formal runtime activation remains separately blocked: a read-only request to
`http://192.168.30.126:5173/api/v1/system/status` on 2026-08-11 returned
`sourceRevision=3422174e7c731a4c4f00e2ae0b15badd14aa3b64514794530ade9b9decc8f63d`
and did not expose `schemaRevision`, `configRevision`, or `runtimeVersion`. This is
deployment evidence, not a code defect. The formal runtime must not execute a guarded
paid Pilot until it is deployed from the synchronized `main` branch and the four
revisions match the Pilot lock.

## Non-Blocking Gaps

- Provider cost in currency remains a proxy (`generationCostCredits`) unless the
  provider supplies an authoritative charge ledger.
- Full black/frozen-frame detection remains delegated to the existing technical QA
  implementation and its configured media backend.

## Minimum Implementation Tasks

- [x] Add human review queue counts to the operations snapshot.
- [x] Add optional Pilot runtime lock comparison and drift alert.
- [x] Normalize monitoring alerts to the three Pilot severities.
- [x] Add critical alerts for paid uncertainty and asset contamination.
- [x] Add success/retry rates and explicit measurement-gap reporting.
- [x] Add automated regression coverage.

## Evidence

Validated with `backend/tests/test_observability_metrics.py`, including empty-data
measurement gaps, asset contamination, and a mismatched runtime lock. The code was
synchronized to both `codex/testing` and `main`. The formal runtime read-only check
above proves that deployment activation remains guarded; this audit does not authorize
or execute paid provider calls.

Implementation outcome: `PASS_WITH_GUARDRAILS`  
Formal runtime activation outcome: `BLOCKED_RUNTIME_DRIFT`
