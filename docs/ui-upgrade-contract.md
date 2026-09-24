# UI Upgrade: State, Recovery, Cost and Permissions

Status: incremental baseline, 2026-09-24. This document does not claim that all stages of
the UI review proposal are implemented. Existing provider submission and settlement
semantics remain unchanged.

## Identity and Authority

| Entity | Stable identity | Current authority |
| --- | --- | --- |
| Video group/task | user ID + clientTaskId; task UUID after creation | ParentTask |
| Video create request | user ID + operation + Idempotency-Key | ApiIdempotencyRecord |
| Image batch | user ID + Idempotency-Key; batch UUID after creation | ImageGenerationBatch |
| Image display group | batch UUID + clientTaskId | ImageGenerationItem rows |
| Output/review | output UUID | persisted output quality decision |

Image clientBatchId is not unique in the current database. A lookup matching more than
one batch is ambiguous and must not pick a batch arbitrarily. Video stateVersion is
authoritative; image timestamps are not advertised as concurrency versions. Local
draft state, selection and progress indicators are never proof of creation or billing.

## Safe Reconciliation API (Implemented)

`POST /api/v1/submission-recovery/query` accepts:

```json
{"kind": "video", "clientId": "stable-group-id", "idempotencyKey": "stable-create-key"}
```

`kind` is `video` or `image`. At least one identity is required. For images `clientId`
means clientBatchId, for videos it means clientTaskId. Both values are placed in the
request body, not a shareable URL. Authentication is mandatory. Even administrators
receive only their own records through this endpoint.

The operation reads local server state only: no provider polling, upload, retry,
creation, quota reservation, or settlement. Its sole write is a recovery audit event.
The response is `Cache-Control: no-store`. The response includes source, checkedAt,
auditId, resourceId, resourceStatus, stateVersion (video only), and:

| state | Meaning | Next action |
| --- | --- | --- |
| submitted | Owned task/batch exists, regardless of generation status | Load existing detail |
| in_progress | Idempotency claim exists, no owned task resolved yet | Bounded safe re-query |
| unknown | Ambiguous records or settled response cannot resolve a resource | Administrator review |
| not_found | No matching visible record; NOT proof that no provider task exists | Administrator review |

`retryAllowed` is always false. This endpoint cannot authorize another paid request.
`submitted` describes local creation only, not provider success or final billing.
No raw cached responses, prompts, titles, URLs, credentials, or provider request IDs
are returned. Audit identity is a SHA-256 digest, with actor, time and result.

An in-progress claim older than 15 minutes requires administrator review. Clients
must stop automatic polling after a bounded window (at most 15 minutes), pause while
offline/hidden/unauthenticated, and expose a manual safe query action. Not-found and
unknown responses must never automatically generate a fresh idempotency key.

## Costs and Limits

Existing server policy is authoritative:

- Image allowance is per server-expanded expected output count, not client group
  count. It is checked under the user lock before creating a batch. Quota rejection
  creates no batch; a subsequently failed batch conservatively still counts today.
- Image allowance and video point allowance are separate. Do not label allowance
  use as an exact supplier invoice or invent currency estimates.
- Video reservation/settlement remains owned by the points service and existing
  generation lifecycle. A new paid variant may incur additional cost.
- A download failure does not authorize regeneration; recover/download the existing
  result first. Unknown provider outcomes are never presumed free.
- Runtime paid-submission pause must not prevent local drafts or safe reconciliation.

## Permission and Sensitive-State Baseline

Current data isolation is per authenticated user; brand/workspace/team isolation is
not yet a domain feature and must not be simulated with a cosmetic selector. Existing
administrator endpoints retain their separate role guards. Recovery does not grant
new edit, review, delivery, delete, or provider-management permissions.

Store only safe configuration and stable references in draft persistence. Do not
store tokens, provider keys, signed source URLs, raw provider responses or original
media in URL/search state. Storage-disabled environments must degrade to memory.
Account changes must not expose another account's locally cached task details.

## Migration and Remaining Work

This additive API needs no database migration and does not change existing create
contracts. Rollback removes its router registration; old clients remain supported.
No feature flag is needed for a dormant additive API. Any future UI exposure must
use the shared progressive-release flag and fall back to existing workflow controls.

The following are not implemented by this baseline and remain release gates for
the corresponding future features:

- Durable video multi-group batch manifest, uploaded-reference persistence, leases
  and revision-checked mutations for cross-device/multi-tab recovery.
- Provider-assisted reconciliation and administrator final classification with
  evidence, redacted provider IDs, bounded escalation queue and audit trail.
- Atomic batch retry/cancel/review APIs with incremental server cost previews.
- Brand/workspace roles, retention policy and cross-workspace cache purge.
- Full 1440/1024/768/390 visual, keyboard, performance and recovery acceptance matrix.

The safe lookup endpoint must not be represented as completing those workflows.
