# G1 Evidence Index

Updated 2026-09-24. Overall gate: INCOMPLETE. This index supersedes stale
"main lacks launch recovery" and "callback decision required" entries in earlier
G1 reports; it does not erase their historical evidence.

Evidence directory: E:/Codex/visualizations/2026/09/23/01a0cdb7-c7c6-7840-ab2f-0c932e004dc2/G1.
All runs use synthetic data and isolated output/DBs. No production restart,
migration, live credentials or paid provider call forms part of this acceptance.

| Gate | Current evidence | Remaining boundary |
| --- | --- | --- |
| S01/S02 idempotency | Image quota/replay and stale submission regression on SQLite/PostgreSQL | Full video independent-session matrix and restart conflict coverage |
| S03 unknown POST | socket-fault-integration.xml and socket-fault-main.xml; image-http-crash-1/result.json and image-http-crash-main/result.json | Other provider execution backends |
| S04 process recovery | Image real POST acceptance then process kill, 1 POST/1 batch/2 replays; launch recovery and known-handle tests on main | Real video/CLI launch crash, pre-submit and known-handle process crash |
| S05 callback | Public route rejects all requests before DB/provider access; callback-disabled-main.xml | Default rejection is approved, not proof of vendor signature support; polling stale observation race still needs review |
| S06 query retries | retry-policy-testing-full.xml: 48 passed; download-retry-main-full.xml: 51 passed | Per-provider scheduling semantics, not just WaveSpeed/Kling API parsers |
| S07 delivery | Truncated length, ENOSPC, expired URL injected into Kling downloader; partial never published; GET-only retry | Other downloaders, interruption of background download thread, workflow-level recovery |
| S08 cancellation | cancel-race-both.xml and cancel-race-main.xml: 4 passed each | Real Runner cancellation/confirmation ordering and settlement integration |
| S09 quota | Image quota concurrency; existing points reservation tests | Full PostgreSQL video final-quota matrix |
| S10 Shanghai date | cross-day-testing.xml, settlement-main-final.xml; repeated unknown no duplicate ledger, old snapshot settlement serialized | Cross-day concurrent recovery with real task lifecycle |
| S11 events | g1-consolidated-testing.xml and g1-consolidated-main.xml: SQLite/PostgreSQL service snapshot+REST ownership | Browser network disconnect/reconnect workflow |
| S12 confidentiality | Logging exception/URL/data URI regressions | Full response, audit, metric and provider-error injection inventory |

## Operational State Contract

- Before provider launch: no claim that remote submission occurred; use persisted command stage.
- Submitted with handle: query the original attempt.provider/task_id; do not route by current default.
- Submission unknown without handle: keep UNKNOWN_AFTER_SUBMIT/WRITE_UNCERTAIN;
  do not resend, release the charge or switch provider automatically.
- Provider success but download failure: retain remote handle and retry delivery only;
  a .part file is not a delivery artifact.
- Cancellation: only pre-dispatch phases allowed; CAS checks phase/version. Local
  cancellation is not evidence of remote cancellation or a refund.
- Callback: 403 KLING_CALLBACK_DISABLED until a separately approved authentication
  contract is implemented. Polling remains the source of progress.
- SSE: snapshot is a refresh hint. REST and persisted records are authoritative;
  Last-Event-ID does not imply event-history replay.

## Required Remaining Deliverables

G1-01/02 identity/event field mapping and G1-03 metrics require a code-backed
inventory, including durations, unknown/recovery counters, idempotency replay and
conflict, quota rejection and delivery failure. Task/user IDs belong in controlled
audit, not metric labels. Existing operational snapshots are not automatically a
complete metric contract. G1-05 diagnostic views and an operator runbook must be
verified against those fields, not merely declared present.

No completion claim is based on summed test counts. Each row must match its actual
scope, both branches, and current source before the G1 gate can close.

## Consolidated Regression

2026-09-24: same 15 test modules executed on codex/testing fa15c38 and main d781c2e.
Each run: 103 passed, zero skipped/deselected. Includes independent PostgreSQL and
SQLite cases, callback rejection, real loopback socket disconnect, retry/date
parsing, download faults, cross-day ledger, stale-session settlement/cancellation,
launch recovery, user-scoped snapshot/REST, quota and log redaction. Evidence:
g1-consolidated-testing.xml (34.49s), g1-consolidated-main.xml (21.79s).
This is a composition regression, not completion of the open boundaries above.

## Observability Inventory

Authoritative existing implementation: services/observability.py operations_snapshot
and _pipeline_performance; api/events.py; adapters/wavespeed.py and
adapters/kling_official_api.py log records. Definitions verified in source:

| Surface | Existing fields | Interpretation / gap |
| --- | --- | --- |
| Queue snapshot | prepared, generation, running, unknown | Current counts, not cumulative event counters |
| Financial snapshot | pointsReserved, pointsConsumed, pointsUncertain, chargeUnknownAttempts | Reservation/attempt aggregates; not proof of supplier invoices |
| Safety metrics | duplicateGenerationTotal, crossTaskConnectionTotal, unknownAfterSubmitRate | Derived database counts/rate; integrity computation has a cache |
| Capacity | generationSlotUtilization, runnerActiveCommandHosts, runnerOrphanProcesses | Current operating state, not latency distributions |
| Pipeline | sampleCount, p50Seconds, p95Seconds for persisted stages | Stage duration from timestamps; not per-HTTP query latency |
| Provider logs | HTTP method/status/duration; download duration/size | Structured LogRecord extras; formatter/export retention still needs verification |
| User SSE | task ID, phase, stateVersion, updatedAt | Authorized snapshots; no durable event replay |

Not yet established as a complete published contract: idempotency replay/conflict
counters, quota rejection counts, recovery outcomes by action, delivery failure
counts, per-operation latency capture and bounded-label export. Do not claim these
exist merely because their code paths log errors. No new metrics table, dependency
or production migration has been introduced by this inventory.
