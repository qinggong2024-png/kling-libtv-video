# Creative Workflow API Contract v1

状态：前端与后端合同冻结草案  
日期：2026-10-12  
用途：定义 Creative OS 前端与 Creative Workflow 服务之间的稳定边界

本文件是 API 合同设计文档，不是运行时 schema，不会自动改变现有 API。当前真实服务仍只允许 test 环境、local object store、fake/replay adapter 和非付费执行。

## 1. Contract Boundary

Creative Workflow API owns:

- creative task orchestration;
- plan and production package revisions;
- authorization scope and version checks;
- candidate review and selection records;
- recovery, reconciliation, unknown execution and stop semantics;
- source and package evidence required by later adapters.

Existing media systems remain authoritative for:

- image generation batches, items and outputs;
- video task creation, provider attempts and polling;
- provider status and remote recovery;
- billing, quota and delivery qualification;
- historical task compatibility.

The Creative Workflow API must never turn a Provider success into human qualification or delivery eligibility.

## 2. Versioning and Encoding

- Contract identifier: `creative-workflow.v1`.
- HTTP content type: `application/json` for commands and reads.
- Task creation remains `multipart/form-data` because the current offline entry accepts the canonical product front image.
- JSON field names remain `snake_case` to preserve the existing runtime response and command contract.
- New fields are additive and optional until a later contract version makes them required.
- Unknown fields must be ignored by the frontend read adapter only when the field belongs to a documented extension area. Unknown command fields must be rejected by the server.
- IDs are opaque strings to the frontend. The frontend must not parse UUIDs or derive business meaning from an ID.
- Timestamps are ISO-8601 strings with an explicit timezone.
- Hashes are lowercase SHA-256 strings unless a field explicitly documents another algorithm.

## 3. API Surface

### 3.1 Create Creative Task

`POST /api/v1/creative-workflow/tasks`

Current request: `multipart/form-data`

Required fields:

```text
product_id: string
front: image file
```

Optional fields:

```text
client_key: string
product_version_id: string
```

The service validates owner scope, file format, file size, dimensions, source hash, local materialization and task idempotency before creating the task.

The response is a `CreativeTaskResponse`.

### 3.2 Read Creative Task

`GET /api/v1/creative-workflow/tasks/{task_id}`

The response is a complete current snapshot. The frontend must replace its cached workflow snapshot with the response after refresh or recovery. It must not merge candidate, authorization or selection state field by field.

### 3.3 Execute Command

`POST /api/v1/creative-workflow/tasks/{task_id}/commands`

The request is a `CreativeCommand`.

Every command must include:

```json
{
  "command_key": "client-generated-idempotency-key",
  "expected_version": 4,
  "action": "select_direction"
}
```

The response is the updated `CreativeTaskResponse`.

The server checks owner scope, command replay identity, expected state version, current stage, package revision, authorization scope, source evidence and action-specific preconditions before mutating state.

## 4. Success Response

```ts
interface CreativeTaskResponse {
  id: string
  status: CreativeTaskStatus
  state_version: number
  snapshot: CreativeTaskSnapshot
  mode: 'OFFLINE_FAKE_ONLY' | 'DRY_RUN' | 'REPLAY' | string
}
```

`state_version` increases after every accepted state mutation. A read operation does not increase it.

The `mode` field describes the execution boundary. The frontend must display or preserve an offline qualification label whenever the mode is `OFFLINE_FAKE_ONLY`, `DRY_RUN` or `REPLAY`.

## 5. Task Status

```ts
type CreativeTaskStatus =
  | 'DRAFT'
  | 'ANALYZING'
  | 'AWAITING_DIRECTION'
  | 'PLAN_READY'
  | 'IMAGE_GENERATING'
  | 'IMAGE_REVIEW'
  | 'STORYBOARD_GENERATING'
  | 'STORYBOARD_REVIEW'
  | 'VIDEO_GENERATING'
  | 'VIDEO_REVIEW'
  | 'ACTION_REQUIRED'
  | 'BLOCKED'
  | 'CANCELLED'
  | 'COMPLETED'
```

These are Creative Workflow stage summaries. They do not replace image batch status, video task phase, Provider attempt status, billing status or delivery status.

The frontend must preserve:

- `UNKNOWN`;
- `WRITE_UNCERTAIN`;
- partial success;
- reconciliation required;
- stopped and revoked states;
- original error codes.

It must not map these values to `COMPLETED` or `FAILED` without an explicit presentation rule.

## 6. Snapshot Contract

```ts
interface CreativeTaskSnapshot {
  asset: CreativeAssetEvidence
  product_version?: ProductVersionEvidence
  facts_snapshot?: FactsSnapshot
  plan?: CreativePlanRevision
  package?: ProductionPackageRevision
  storyboard?: StoryboardState
  packages?: Record<string, ProductionPackageRevision>
  authorization?: AuthorizationEnvelope
  candidates: CreativeCandidate[]
  selection?: SelectionRecord
  selections?: Record<string, SelectionRecord>
  latest_review?: ReviewRecord
  latest_reviews?: Record<string, ReviewRecord>
  execution_state?: ExecutionState
  stop_reason?: string
  stopped?: boolean
  trace: string[]
  calls: number
  cost_micros: number
  total_calls: number
  total_cost_micros: number
}
```

The server may add stage-specific fields under `storyboard`, `packages`, `selections` and `latest_reviews`. The existing `package`, `authorization`, `candidates`, `selection` and `latest_review` fields remain compatible with the current Director Studio.

### 6.1 Asset Evidence

```ts
interface CreativeAssetEvidence {
  owner_id: string
  object_key: string
  sha256: string
  width: number
  height: number
  source_type: 'USER_UPLOAD' | string
  role: 'PRODUCT' | 'FIRST_FRAME' | 'STORYBOARD' | string
  view: string
  evidence_status: 'OBSERVED_REFERENCE' | 'USER_CONFIRMED' | 'USER_ASSUMED' | 'UNDECIDED' | string
  materialized: boolean
  revoked?: boolean
  license_status?: string
  retention_policy?: string
}
```

`object_key` is an evidence reference. It is not a browser URL and must not be submitted to a Provider by the frontend.

### 6.2 Plan Revision

```ts
interface CreativePlanRevision {
  revision: number
  facts_revision: number
  directions: DirectionCandidate[]
  selected_direction?: 'A' | 'B' | 'C' | null
  claims?: GroundedClaim[]
  locks?: Record<string, unknown>
  source_hash?: string
  facts_snapshot_hash?: string
  evidence?: string
}
```

### 6.3 Production Package

```ts
interface ProductionPackageRevision {
  package_id: string
  revision: number
  parent_package_id: string | null
  locks_hash: string
  facts_revision: number
  preservation_hash: string
  ruleset: string
  purpose: 'FIRST_FRAME' | 'VIDEO_STORYBOARD'
  shot_id: 'FIRST_FRAME' | 'SHOT_01' | string
  source_first_frame_candidate_id?: string
  prompt: string
  reality: RealityDecision[]
}
```

The package prompt, lock hash, preservation hash and reality decisions are server-owned immutable evidence. The frontend may display them and pass their identifiers through a future handoff, but must not reconstruct or rewrite them.

### 6.4 Authorization

```ts
interface AuthorizationEnvelope {
  authorization_id: string
  package_id: string
  locks_hash: string
  scope: 'FIRST_FRAME' | 'VIDEO_STORYBOARD'
  shot_ids: string[]
  expires_at: string
  loop_enabled: boolean
  max_revisions: number
  max_calls: number
  max_cost_micros: number
  currency: string
  allowed_modules: string[]
  parent_authorization_id?: string | null
  total_task_cap_micros?: number | null
}
```

An authorization is scoped to a package revision. A package, lock hash, source evidence, scope, shot list, expiry, budget or permission change invalidates the authorization.

### 6.5 Candidate, Review and Selection

```ts
interface CreativeCandidate {
  candidate_id: string
  package_id: string
  authorization_id: string
  shot_id: string
  batch_id: string
  item_id: string
  output_id: string
  synthetic: boolean
  qualified: boolean
  revision_index: number
  sha256: string
  object_key: string
  media_evidence: string
}

interface ReviewRecord {
  candidate_id: string
  reviewer_id: string
  reviewer_kind?: 'HUMAN' | 'FAKE_CRITIC' | string
  decision: 'QUALIFIED' | 'REJECTED' | 'UNVERIFIED'
  qualification_scope: string
  reason: string | null
  shot_id?: string
}

interface SelectionRecord {
  candidate_id: string
  package_id: string
  shot_id: string
  batch_id?: string
  item_id?: string
  output_id?: string
  order?: number
  synthetic?: boolean
}
```

Selection is not approval. `QUALIFIED` is not delivery eligibility. `OFFLINE_SYNTHETIC_ONLY` is never a production qualification scope.

## 7. Command Contract

```ts
type CreativeCommandAction =
  | 'analyze'
  | 'select_direction'
  | 'authorize'
  | 'generate'
  | 'review'
  | 'select'
  | 'revise'
  | 'stop'
  | 'revoke_asset'
  | 'reconcile'
```

Common command fields:

```ts
interface CreativeCommand {
  command_key: string
  expected_version: number
  action: CreativeCommandAction
  direction_id?: 'A' | 'B' | 'C'
  authorization?: AuthorizationEnvelope
  package_id?: string
  candidate_id?: string
  shot_id?: string
  decision?: 'QUALIFIED' | 'REJECTED'
  changed_modules?: string[]
  fix?: string
  failure_region?: string
  fake_outcome?: 'SUCCEEDED' | 'UNKNOWN' | 'WRITE_UNCERTAIN'
  reconcile_not_submitted?: boolean
  client_key?: string
  reason?: string
  impact_scope?: string
}
```

Action ownership:

| Action | Meaning | May create Provider work |
| --- | --- | --- |
| `analyze` | Create or refresh the planning analysis | No in the current contract |
| `select_direction` | Persist a human direction choice | No |
| `authorize` | Persist a scoped package authorization | No by itself |
| `generate` | Run the currently authorized Fake/Replay stage | No; current mode is offline only |
| `review` | Persist a candidate review decision | No |
| `select` | Persist a human candidate selection | No |
| `revise` | Compile a new package revision within authorization | No in current frontend scope |
| `stop` | Stop an authorized loop or stage | No |
| `revoke_asset` | Revoke source evidence and block dependent execution | No |
| `reconcile` | Resolve unknown or write-uncertain execution evidence | No automatic resubmission |

Future real execution must use a separately approved command or execution contract. It must not silently change the meaning of `generate`.

## 8. Error Contract

Current HTTP error body:

```json
{
  "detail": {
    "code": "STALE_VERSION",
    "message": "STALE_VERSION",
    "current_version": 5
  }
}
```

Stable error fields:

```ts
interface CreativeWorkflowError {
  code: string
  message: string
  current_version?: number
  current_state_version?: number
  field_errors?: Array<{ field: string; message: string }>
}
```

The frontend must treat these codes as control signals:

```text
STALE_VERSION
IDEMPOTENCY_CONFLICT
TASK_IDEMPOTENCY_CONFLICT
EXECUTION_UNKNOWN
WRITE_UNCERTAIN
RECONCILIATION_REQUIRED
AUTHORIZATION_SCOPE_INVALID
AUTHORIZATION_EXPIRED
STALE_PACKAGE
STALE_CANDIDATE_PACKAGE
ASSET_HASH_MISMATCH
ASSET_REVOKED
ASSET_NOT_MATERIALIZED
TEXT_CONTRACT_REJECTED
OFFLINE_WORKFLOW_DISABLED
PAID_MODE_NOT_ALLOWED
```

Unknown error codes must remain visible in technical details and must not be downgraded to a retry or success action.

## 9. Frontend Ownership Rules

The frontend may own:

- Creative Brief editing;
- direction candidate presentation;
- selected direction display;
- package and evidence presentation;
- command idempotency key generation;
- stale-version refresh and user-visible recovery actions;
- read-only handoff context construction.

The frontend must not own:

- Provider task IDs as a replacement for server attempts;
- billing, quota or actual cost;
- final qualification or delivery eligibility;
- package Prompt compilation;
- source hash verification;
- recovery decisions after `UNKNOWN` without a server reconciliation response;
- a second CreativeTask state machine.

## 10. Handoff Boundary

The frontend-only handoff prepared in Milestone 5 remains a read-only context:

```ts
interface StudioHandoffContext {
  source: 'director-studio'
  projectId?: string
  directionId: 'A' | 'B' | 'C'
  packageId: string
  packageRevision: number
  shotId: 'FIRST_FRAME' | 'SHOT_01'
  references: {
    productFront: boolean
    selectedDirection: boolean
    productionPackage: boolean
  }
}
```

It is not an image or video task request. It does not contain Provider URLs, browser `File` objects, billing authorization or a claim that a Fake candidate is production qualified.

The future production bridge must accept only a server-validated package and materialized source mappings. It must revalidate owner, package revision, lock hash, source hash, qualification, license, budget, authorization expiry and current execution state immediately before submission.

## 11. Compatibility Requirements

- Existing `?view=images`, `?view=make`, `?task=id`, `?view=records` and `?view=library` behavior is unchanged.
- Existing ImageStudio and VideoStudio task contracts remain unchanged.
- Existing historical video tasks remain queryable and recoverable.
- Existing `FIRST_FRAME` and `SHOT_01` scope identifiers remain stable.
- Older clients that do not send new optional fields continue to receive the current offline behavior.
- The server must not require a new frontend route for Director Studio.
- The frontend must preserve raw server snapshots for diagnostics even when it cannot render a newly added extension field.

## 12. Freeze Checklist

The following items are defined for review and are not silently approved by this document:

- [x] Existing endpoint paths and current response envelope.
- [x] `state_version` and `command_key` concurrency/idempotency rules.
- [x] Separation between CreativeTask summary and media execution state.
- [x] Package revision, lock hash, preservation hash and source evidence references.
- [x] Separate first-frame and storyboard scopes.
- [x] Selection, qualification and delivery semantics.
- [x] Dry-run/replay prohibition on actual Provider submission.
- [ ] Final real Provider request and materialization contract.
- [ ] Paid budget, quota reservation and ledger transaction contract.
- [ ] Real Provider capability and license acceptance evidence.
- [ ] PostgreSQL, multi-worker and crash-recovery proof.
- [ ] Human Checkpoint 1 acceptance.

Until the unchecked items are accepted, the frontend must remain in planning, read-only handoff and offline validation scope.
