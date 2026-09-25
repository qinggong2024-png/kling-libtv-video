# G1 Evidence Index

Updated 2026-09-24. Overall gate: INCOMPLETE. This index supersedes stale
"main lacks launch recovery" and "callback decision required" entries in earlier
G1 reports; it does not erase their historical evidence.

Evidence directory: E:/Codex/visualizations/2026/09/23/01a0cdb7-c7c6-7840-ab2f-0c932e004dc2/G1.
All runs use synthetic data and isolated output/DBs. No production restart,
migration, live credentials or paid provider call forms part of this acceptance.

| Gate | Current evidence | Remaining boundary |
| --- | --- | --- |
| S01/S02 idempotency | Image quota/replay and stale submission regression; video create concurrent replay/conflict and fresh-app replay on SQLite/PostgreSQL | Video confirmation/paid dispatch matrix and actual process restart conflict coverage |
| S03 unknown POST | socket-fault-integration.xml and socket-fault-main.xml; image-http-crash-1/result.json and image-http-crash-main/result.json | Other provider execution backends |
| S04 process recovery | Image real POST acceptance then process kill; video API launch entered then process kill with recovery counts [1,0], UNKNOWN_AFTER_SUBMIT/UNCERTAIN reservation and zero resubmits; launch recovery and known-handle tests on main | Pre-submit crash and known-handle process crash for the video path; CLI-specific provider execution |
| S05 callback | Public route rejects all requests before DB/provider access; callback-disabled-main.xml; conditional polling writes reject stale terminal/version observations | Default rejection is approved, not proof of vendor signature support; internal callbacks must not be re-enabled without a shared concurrency/authentication contract |
| S06 query retries | retry-policy-testing-full.xml: 48 passed; download-retry-main-full.xml: 51 passed | Per-provider scheduling semantics, not just WaveSpeed/Kling API parsers |
| S07 delivery | Truncated length, ENOSPC, expired URL injected into Kling downloader; partial never published; GET-only retry | Other downloaders, interruption of background download thread, workflow-level recovery |
| S08 cancellation | cancel-race-both.xml and cancel-race-main.xml: 4 passed each | Real Runner cancellation/confirmation ordering and settlement integration |
| S09 quota | Image quota concurrency; video-quota-testing.xml and video-quota-main.xml: 2 passed each, SQLite/PostgreSQL final quota, user isolation and reservation replay | Full video API confirmation lifecycle remains separate from reservation-service coverage |
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

## Video Create Increment

video-idempotency-testing.xml: 2 passed, SQLite/PostgreSQL. Concurrent independent
HTTP request sessions return the same created task. A fresh application/client
replays the persisted response and rejects a changed payload with 409
IDEMPOTENCY_KEY_REUSED. Exactly one task and idempotency record exist, with zero
attempts, points reservations or fake-provider submissions. This is a create-only
contract test, not a process-kill or paid dispatch test. Main verification is
recorded separately in video-idempotency-main.xml after scoped promotion.

## Polling Observation Race

Confirmation increment: confirmation-testing.xml and confirmation-main.xml each
passed one SQLite HTTP workflow test using fake analysis/materialization and
disabled automatic dispatch. Concurrent same-key confirmation and later replay
return identical responses; changed payload returns IDEMPOTENCY_KEY_REUSED.
Exactly one attempt, command, reservation and confirmation idempotency row exist,
with zero generation calls. This is foreground confirmation coverage only;
PostgreSQL, background confirmation, fresh-process replay and actual paid-dispatch
lifecycle coverage remain open.

Stale confirmation-claim sweep: stale-confirm-testing.xml and
stale-confirm-main-fixed.xml each passed 8 tests. The production service runtime
now includes the same bounded five-minute sweep and `STALE_CLAIM_GRACE` helper as
testing. Settled and live claims are preserved; abandoned response-less claims
are deleted in bounded batches. The first main run failed at collection because
the implementation and test were absent; that negative evidence is retained by
the command output and is not counted as a pass.

poll-race-before.xml reproduced four failures: a stale running response or query
error overwrote independently committed success on SQLite and PostgreSQL. Polling
now conditionally acquires a write guard using RUNNING status and state_version
after query I/O (and before timeout handling). A changed row rejects the stale
observation. Successful guards increment the version and refresh the attempt.
Original-provider adapter selection and task identity are unchanged.

poll-race-testing.xml: 27 passed, including 12 independent-session poll cases,
13 launch recovery cases and 2 video create cases. Cases cover terminal changes,
newer nonterminal versions and normal unchanged observations with success/error
query responses. Main verification uses poll-race-main.xml. No live supplier,
callback authentication or browser lifecycle coverage is implied.

## Image Polling Race

image-poll-race-before.xml reproduced terminal state regression on SQLite and
PostgreSQL. API batch reads now happen inside the refresh lock; service-level
conditional writes compare persisted item status and last_polled_at so independent
workers also reject stale observations. Output collections are refreshed under
the write guard and batch aggregation reloads persisted item states under a
batch write lock. Failed flushes are rolled back and propagated, not committed.

image-poll-race-testing.xml: 18 passed, including four independent-session cases
and the existing image batch suite. Two preloaded sessions produce one output,
one materialization and no extra generation POST. Main verification is recorded
in image-poll-race-main.xml. This does not prove process interruption during an
image download or full frontend account isolation.

## Video Launch Crash Drill

`scripts/g1-video-crash.py` ran in an isolated SQLite directory with a synthetic
provider adapter. The worker persisted `LAUNCH_STARTED`, entered provider
submission, and was force-terminated. A fresh process ran stale launch recovery
twice: counts `[1, 0]`. The result was `UNKNOWN_AFTER_SUBMIT`, command
`UNCERTAIN`, reservation `UNCERTAIN`, ledger `RESERVE + UNCERTAIN`, and zero
provider calls after restart. Evidence: `G1/video-crash-run4/result.json`.
This is API-backend launch coverage only; it does not establish pre-submit or
CLI execution-backend crash semantics.

Follow-up HTTP drill uses the real KlingOfficialApiAdapter.submit and HTTP
transport, replacing only payload construction with synthetic data. A loopback
receiver fsyncs one POST before the caller kills the worker while its response is
pending. Recovery asserts one persisted POST, no remote handle, zero calls to a
fail-on-submit recovery adapter, counts [1,0], and RESERVE + UNCERTAIN ledger.
Testing evidence: video-http-crash-testing/result.json. Main evidence is recorded
in video-http-crash-main/result.json after independent execution. This closes the
API HTTP-acceptance fault point, not pre-submit/known-handle/CLI crash coverage.

Known-handle follow-up: `scripts/g1-video-crash.py ROOT submit known` returns a
synthetic task ID over real loopback HTTP, commits RUNNING/PROCESS_STARTED, and
waits for force termination. `recover known` in a fresh process verifies [0,0]
launch recoveries, one original-provider query of the same saved ID, one total
POST, zero new submissions, RUNNING and RESERVED. Default adapter is a forbidden
sentinel while the persisted provider maps to the query adapter. Evidence:
video-known-testing/result.json and video-known-main/result.json. This covers
polling resumption after a saved-handle crash, not terminal download/settlement.

Pre-launch follow-up: `submit before` is killed during synthetic object-store
localization before LAUNCH_STARTED. A fresh `recover before` verifies READY,
no remote ID, no POST ledger and zero stale-launch recoveries, then resumes the
same persisted command through the real API submit transport. Final assertions:
one POST, one reservation, one RESERVE ledger entry and RUNNING. Evidence:
video-before-testing/result.json and video-before-main/result.json. Scope is
direct persisted-command resume; scheduler lease acquisition and CLI-host crash
recovery remain distinct requirements, not covered by this fixture.

### Confirmed Claimed-Command Gap

CLI submission exception follow-up: cli-submit-unexpected-testing.xml and
cli-submit-unexpected-main.xml each passed 14 launch/recovery tests, including a
Kling adapter that raises an unexpected exception after the durable
`LAUNCH_STARTED` commit. The runner now records `UNCERTAIN` /
`UNKNOWN_AFTER_SUBMIT` and keeps the reservation uncertain instead of aborting
the queue with a stranded launch. Exceptions before the launch marker still
propagate as pre-submit failures. This is adapter/backend fault coverage, not a
real CLI executable or paid-provider test.

`submit claimed` reproduces the scheduler's committed CLAIMED/LAUNCHING handoff
and then force-kills the actual worker during localization before any HTTP POST.
Fresh-process recovery twice leaves CLAIMED/LAUNCHING with counts [0,0]. Evidence:
video-claimed-testing/result.json and video-claimed-main/result.json, explicitly
marked FAIL_UNRECOVERED_CLAIM. The harness exits normally only to save this known
negative evidence; that is NOT an acceptance pass. This blocks the S04 gate.
Recovery must fence the old owner's pre-submit transition before making an
expired claim dispatchable, otherwise a slow old worker could still submit.

Repair follow-up: run_ready now recovers expired pre-launch claims only when no
launch/submission timestamp or remote ID exists. It preserves reservations,
releases capacity and restores READY/DISPATCH_PENDING. Submission uses a
conditional command status/owner/lease transition; stale workers return without
releasing the new owner's capacity. claim-fence-testing.xml: 19 passed including
SQLite/PostgreSQL claim fencing and existing launch recovery. Main verification
is claim-fence-main.xml. Earlier process evidence remains a historical failure;
fixed full scheduler process replay and slow-worker error paths need expansion.

Scheduler follow-up: scheduler-crash-testing/result.json and
scheduler-crash-main/result.json use real run_ready claiming/capacity acquisition,
kill during localization, then fresh-process run_ready after isolated lease expiry.
Assertions require one POST, PROCESS_STARTED/RUNNING, no occupied capacity slots,
one RESERVED reservation and one RESERVE ledger. claim-slow-testing.xml and
claim-slow-main.xml cover 10 SQLite/PostgreSQL cases including a slow old worker
returning or raising after claim recovery; neither path may submit or settle.
These supersede the prior claimed-command failure for this tested recovery path.

## Consolidated Regression

2026-09-24: same 15 test modules executed on codex/testing fa15c38 and main d781c2e.
Each run: 103 passed, zero skipped/deselected. Includes independent PostgreSQL and
SQLite cases, callback rejection, real loopback socket disconnect, retry/date
parsing, download faults, cross-day ledger, stale-session settlement/cancellation,
launch recovery, user-scoped snapshot/REST, quota and log redaction. Evidence:
g1-consolidated-testing.xml (34.49s), g1-consolidated-main.xml (21.79s).
This is a composition regression, not completion of the open boundaries above.

## Observability Inventory

Image quota metric: API quota rejection now commits an IMAGE_QUOTA_REJECTED
AuditEvent before returning 429, without retaining the idempotency key or payload.
The admin snapshot publishes imageQuotaRejectionCount for seven days; actor
identity remains in controlled audit only. Each rejected request counts once;
successful idempotent replay counts zero. quota-metrics-testing.xml covers
10 SQLite/PostgreSQL quota/concurrency cases. Initial main verification failed
(8 failed, 2 passed): promotion omitted the AuditEvent import already present
on testing. Negative evidence is retained in
quota-metrics-main-missing-import.xml. After promoting the missing import,
quota-callback-main-fixed.xml passed 17 quota/concurrency/callback cases.
This metric does not include video quota rejection, which remains unimplemented.

### Approved Callback Contract Reverification

callback-contract-testing-verified.xml and callback-contract-main-verified.xml
each passed 32 tests: quota metrics/concurrency, fail-closed callback, delivery
recovery and launch recovery. The public callback remains disabled before body,
DB or provider access. Existing attempts retain original-provider polling and
delivery; delivery recovery asserts one consumption entry without resubmission.
These isolated tests do not certify vendor authentication, real media delivery,
production deployment or overall G1 completion. The earlier
callback-contract-testing.xml contains a command-path error (zero tests), not
acceptance evidence. No production restart, migration or paid call was performed.

Thread cancellation follow-up: all four video adapters stage downloads in a
blocking worker but publish via the async caller only after successful completion.
Cancellation/timeout drains the worker and removes staging before propagating.
download-cancel-testing.xml: 62 passed; download-cancel-main.xml: 61 passed,
covering normal publication, cancellation, repeated cancellation, timeout and
existing provider faults. Drain can exceed the requested timeout while blocking I/O finishes;
this is not a hard wall-clock deadline or proof against indefinite peer trickle.

Downloader expansion: download-providers-before.xml reproduced truncation
publication in Kling CLI, WaveSpeed video and Bach (3 failures, 9 passes).
All three now compare received bytes with declared Content-Length before rename.
download-providers-testing.xml: 35 passed; download-providers-main.xml: 34 passed,
including four providers x truncation/ENOSPC/expired URL, no partial publication,
temporary cleanup and GET-only recovery. HTTP responses are injected; background
thread cancellation and real network interruption remain separate coverage gaps.

Delivery resume follow-up: delivery-resume-before.xml reproduced loss of a saved
remote task ID on SQLite/PostgreSQL when the persisted output payload lacked taskId.
Success handling now retains the existing handle when the result omits it.
delivery-resume-testing.xml and delivery-resume-main.xml cover resume in a fresh
session, original-provider adapter selection, one READY artifact, one CONSUME
ledger entry and a no-op second resume (2 SQLite/PostgreSQL cases on both branches).
Downloads, object storage and technical validation are synthetic in this suite;
it does not claim real media or download-thread interruption verification.

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

The published snapshot now makes the established units and scope explicit:
`unknownAfterSubmitRate` uses launched attempts in a seven-day window,
`pointsReserved/Consumed/Uncertain` retain each branch's quota semantics with explicit
units (testing: generation reservation counts; main: historical estimated points),
`runnerActiveCommandHosts` counts distinct assigned hosts, and
`deliveryFailureCount` counts failed download artifacts in the same window.
Evidence: `observability-testing.xml`, 10 passed. Remaining unestablished
contract items are idempotency replay/conflict counters, quota rejection counts,
recovery outcomes by action, per-operation HTTP latency capture, and bounded-label
external export. Logs are not treated as durable metrics; no new metrics table,
dependency or production migration has been introduced.
