# G1 Safe Recovery Runbook

Scope: existing task recovery and diagnosis, not permission to deploy, mutate a
production database, restart services or make paid calls. Production is
http://192.168.30.126:5173/. A localhost instance is not production.

## Identity Map

| Business identity | Persistent source | Join / interpretation |
| --- | --- | --- |
| Video request | ParentTask.id / client_task_id / user_id | Owner-scoped task; not a provider ID |
| Video result branch | GenerationVariant.id / parent_task_id | One task can own multiple variants |
| Paid attempt | GenerationAttempt.id / variant_id / intent_hash | Attempt records provider and task_id; keep original provider when querying |
| Dispatch | GenerationCommand.id / attempt_id / status | LAUNCH_STARTED precedes provider acceptance; PROCESS_STARTED is later |
| Quota | PointsReservation.attempt_id / business_date | Shanghai reservation date remains authoritative across midnight |
| Ledger | PointsLedger.attempt_id / entry_type | RESERVE, UNCERTAIN, CONSUME, RELEASE are not interchangeable |
| Video delivery | DownloadArtifact.attempt_id / status | READY artifact, not a remote URL or .part file, is delivery evidence |
| Image batch | ImageGenerationBatch.id / client_batch_id / idempotency_key / user_id | Replay identity belongs to this owner and manifest |
| Image prediction | ImageGenerationItem.batch_id / provider_task_id / status | Never infer safe resubmission solely from missing remote ID |
| Image output | ImageGenerationOutput.item_id / object_key / sha256 | Stored material and quality decision are distinct from generation success |

Verify field ownership with domain/models.py, services/image_generations.py,
services/points.py and runner/supervisor.py. Do not paste raw identifiers into
public screenshots or use user/task IDs as monitoring labels.

## Diagnose Before Acting

1. Identify the owner and original client identity. Keep the idempotency key stable;
   do not generate a new key merely because the browser timed out.
2. Query `POST /api/v1/submission-recovery/query` with kind and clientId and/or
   idempotencyKey using the user's authenticated session. This API performs only
   local database lookup and returns an auditId. Never put the key in a URL.
3. Interpret `submitted` as a local resource found, not proof of remote acceptance.
   Inspect resourceStatus and resourceId through the normal owner-scoped detail API.
   `in_progress`, `unknown`, and `not_found` are not authorization to resubmit:
   retryAllowed is always false on this lookup endpoint.
4. Re-query REST after notifications disconnect. SSE snapshots are refresh hints;
   Last-Event-ID does not provide durable event-history replay.

| Observed state | Safe interpretation | Permitted recovery path |
| --- | --- | --- |
| Before launch | No evidence yet that remote generation was submitted | Existing dispatch gates; do not bypass budget/consent |
| LAUNCH_STARTED without handle | Provider may have accepted before process death | Expired-launch recovery marks uncertainty; no new POST |
| Expired Kling launch with handle | Remote task is queryable | Recovery returns eligible attempt to RUNNING; original-provider polling owns progress |
| UNKNOWN_AFTER_SUBMIT / WRITE_UNCERTAIN | Spend and result unresolved | Administrator review; no auto-refund, no provider switch, no blind resubmit |
| Remote success, download failed | Generation succeeded; delivery is incomplete | Existing output restoration/download path only |
| CANCELLED | Local cancellation succeeded in allowed pre-dispatch phase | Not proof of remote cancellation or refund |

## Administrator Reconciliation

Use existing `GET /api/v1/admin/reconciliations` and the authorized classify
workflow under `/api/v1/admin/reconciliations/{attempt_id}/classify`. Check the
current API schema, role checks and evidence requirements before acting; do not
fabricate provider billing evidence. The local ledger is not a supplier invoice.
Preserve original attempt identity and the evidence supporting the decision.

For known successful video output, the existing task restore endpoint is
`POST /api/v1/tasks/{task_id}/restore-remote-output`. Validate ownership, variant
and current restore contract. It is a recovery action, not a new generation request.
Do not delete .part files or change artifact status in production by hand.

## Callback And Logs

Public Kling callbacks return 403 KLING_CALLBACK_DISABLED until an authenticated
contract is implemented and separately reviewed. Do not add a made-up signature
header, disable this gate to clear errors, or treat callbacks as billing authority.
Polling/download/settlement must remain available when new submissions pause.

Rotating diagnostic logs preserve numeric duration_ms, size_bytes, count,
http_status and allowlisted http_method. Arbitrary extras are not exported.
Idempotency events are idempotency.replay, idempotency.conflict and
idempotency.in_progress, each with count=1. These are process log observations,
not a guaranteed durable metric store or exactly-once accounting events.
Never copy raw provider responses, signed URLs, credentials, original media or
prompts into issue reports. Log rotation may remove old records; retain redacted
acceptance evidence separately.

## Stop Conditions And Evidence

Stop new test submissions on duplicate paid POST, quota overflow, cross-user data
exposure or production-path access. Preserve safe query/delivery/settlement paths.
Record code SHA, isolated environment, exact test result, fault location, request
count, state/ledger assertions and output checksum. A passing helper test does not
prove an unexecuted full workflow. Use G1_EVIDENCE_INDEX.md for current gaps.

Deployment and business acceptance remain separate from source synchronization.
No release approval is implied by this runbook.
