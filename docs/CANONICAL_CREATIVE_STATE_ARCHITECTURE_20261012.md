# Canonical Creative State Architecture

日期：2026-10-12  
状态：架构提案，等待人工评审  
范围：Creative Workflow 的统一创意真源设计  
执行边界：本文件只定义架构、边界、迁移和优先级，不实现代码、迁移、Provider 接线或生产写入。

## 1. 决策摘要

项目已经具备 ProductVersion、导演任务、Reality/Spatial 准备合同、生产包、镜号映射、Provider 预检、Quality 证据和恢复/记忆能力，但它们目前由不同对象分别保存。继续按功能增加状态会让同一个创意事实出现多个可竞争的版本。

本提案建立一个以 `CreativeState` 为唯一创意真源的聚合：

```text
CreativeState
├── ProductState
├── CharacterState
├── SceneState
├── SpatialState
├── CameraState
├── StoryboardState
├── ShotState[]
└── QualityState
```

`CreativeState` 只拥有创意事实、身份连续性、镜头意图、锁项和证据引用。它不拥有 Provider 任务状态、费用、配额、远端任务 ID、媒体下载状态或正式交付资格。

每次可执行生产都绑定一个不可变的 `CreativeStateRevision`。图片、视频和质量流程只能读取这个 revision，并通过 adapter 转换为既有请求和任务合同。任何输入事实、锁项、镜头计划或人工选择改变，都派生新 revision，不原地改写已绑定的 revision。

建议的首版落点：

```text
CreativeState aggregate
  ├─ current_revision pointer
  ├─ immutable revision snapshots
  ├─ append-only records and evidence references
  └─ adapters for legacy task, director, image, video, quality and handoff paths
```

这是一层统一的创意编排模型，不是新的 Provider 队列、第二套任务状态机或独立 AI agent。

## 2. 当前架构映射

| Existing System | 当前实际位置 | 当前责任 | 未来角色 | 决策 |
| --- | --- | --- | --- | --- |
| Product / ProductVersion | `backend/src/libtv_agent/domain/models.py`、`api/products.py`、`services/product_versions.py` | 保存商品身份、版本、来源、truth/immutable fields、allowed variation、许可和状态 | `ProductState` 的持久来源；为每个 `CreativeStateRevision` 提供不可变 product snapshot | canonical source + adapter |
| CharacterDNA | `frontend/src/creative-project/reality.ts` 的 `CharacterDNA`；由 `CreativeIntelligenceSnapshot` 承载 | 描述人物身份、外观连续性、行为和证据 | `CharacterState` 的 schema/read model；未来由 Creative State revision 持有引用和快照 | canonical state component；保留前端 adapter |
| SceneDNA | `frontend/src/creative-project/reality.ts` 的 `SceneDNA` | 描述环境、灯光、空间锚点和连续性 | `SceneState` 的 schema/read model | canonical state component；保留前端 adapter |
| Reality Snapshot | `frontend/src/creative-project/reality.ts`、`realityAdapters.ts`；后端 `creative/workflow.py` 的六维 Reality | 汇总 DNA、证据、模式和 preflight 状态 | `CreativeState` 的 evidence/index 层；六维决策进入 revision 的 `reality` 部分 | canonical evidence/reference, not an independent owner |
| Spatial DNA / contracts | `frontend/src/features/spatial-understanding/contracts.ts`、`docs/SPATIAL_UNDERSTANDING_PREPARATION_V1.md` | 离线空间、深度、相机关系和遮挡准备 | `SpatialState`；以后可被 shot 继承 | canonical state component；当前 adapter |
| Camera DNA / Camera relationship | `frontend/src/creative-project/reality.ts`、spatial contracts、video blueprint types | 相机取景、镜头、运动和主体关系 | `CameraState`；与 Scene geometry 和 SpatialState 建立引用 | canonical state component |
| Director plan / direction candidates | `backend/src/libtv_agent/creative/workflow.py`、`services/creative_workflow.py`、`frontend/src/features/director-studio` | 商品事实、方向候选、人工选择、Reality、生产包编译 | `StoryboardState.campaign` 和 direction history 的输入 | adapter first; direction record becomes canonical only after selection |
| Production package revisions | `CreativeTask.snapshot_json`、`CreativeRecord`、`creative/text_contract.py`、前端 `ProductionPackage` | 锁项、Prompt、Reality、facts revision、package lineage 和 Preservation | `CreativeStateRevision.productionPackage` / compiled shot package | canonical revision artifact; old storage adapted |
| Storyboard objects | Director snapshot `storyboard.packages/candidates/selections/latest_reviews`；legacy `ParentTask.assets` | 分镜包、候选、审核选择、顺序和恢复 | `StoryboardState` plus explicit `ShotState[]` | canonical state after migration; legacy path adapter |
| Shot mappings | `productionBridge.ts`、`creative_video_bridge.py`、`creative/handoff.py`、`shot_id` mappings | 将镜号绑定到 package、candidate、batch/item/output 和最终输入 | `ShotState.sourceBindings` for creative identity; execution IDs remain Provider/Task layer | split ownership |
| Kling subject references | `services/kling_preparation.py`、`VideoTaskCreate.element_ids`、`SubjectElementJob`、frontend Kling panels | 校验参考顺序、元素数量、素材物化和 Kling request 参数 | `ProviderReferencePlan` adapter generated from Product/Character/Shot state | adapter; provider layer owns execution |
| Provider request objects | `services/creative_provider_requests.py`、`creative_provider_submission*.py`、`ProviderSubmissionTicketRecord` | 生成 dry-run/replay request、锁定 Prompt、输入 manifest、票据、幂等和 UNKNOWN 边界 | `ProviderAdapter` input; never a creative truth source | adapter / provider boundary |
| Quality contracts | `backend/src/libtv_agent/quality/`、`ValidationResult`、`ImageGenerationOutput.quality_gates_json`、`creative/media_qualification.py` | 技术校验、证据观察、人工审核、资格和交付门 | `QualityState` records evidence and decisions; formal task/qualification state remains existing quality/task owner | canonical evidence record; task status adapter |
| Creative Memory | `frontend/src/creative-project/memory*.ts` | 项目内方向、选择、package revision、bridge decision 的 append-only 历史 | history projection of CreativeState events | adapter/history projection |
| Recovery / handoff | `directorRecovery.ts`、`creative/handoff.py`、`CreativeTaskRecoveryReference` | 记录可恢复的 revision、产品引用、镜号和下一动作 | recovery projection derived from canonical revision and execution records | adapter |

### 2.1 关键结论

当前不存在完整的、服务端可验证的 CharacterState、SceneState 或 SpatialState 权威持久化对象。前端 `CreativeProject.intelligenceSnapshot` 和离线 Spatial contracts 可以作为输入和展示适配器，但不能直接作为 Provider 生产真源。

`CreativeTask.snapshot_json` 已经承担部分聚合快照职责，`CreativeRecord` 已经提供 append-only 记录，`CreativeCommand` 已经提供命令幂等边界。它们应被演进为 `CreativeState` 的持久实现基础，而不是被另建一套平行存储。

## 3. Proposed CreativeState Model

### 3.1 聚合身份与版本

```ts
type CreativeState = {
  schemaVersion: 'creative-state.v1'
  creativeStateId: string
  ownerId: string
  projectId?: string
  productRef: ProductRef
  currentRevision: number
  stateVersion: number
  status: CreativeStateStatus
  product: ProductState
  character?: CharacterState
  scene?: SceneState
  spatial?: SpatialState
  camera?: CameraState
  storyboard: StoryboardState
  shots: ShotState[]
  quality: QualityState
  evidence: EvidenceIndex
  provenance: Provenance
}
```

`CreativeState` 是当前指针和聚合摘要。它不允许业务代码直接修改嵌套对象。写入必须通过命令生成新的 `CreativeStateRevision`，并在同一事务中推进 `stateVersion`。

```ts
type CreativeStateRevision = {
  creativeStateId: string
  revision: number
  parentRevision: number | null
  stateVersion: number
  factsRevision: number
  schemaVersion: 'creative-state.v1'
  contentHash: string
  locksHash: string
  sourceSnapshotHash: string
  createdBy: string
  createdAt: string
  reason: RevisionReason
  product: ProductState
  character?: CharacterState
  scene?: SceneState
  spatial?: SpatialState
  camera?: CameraState
  storyboard: StoryboardState
  shots: ShotState[]
  quality: QualityState
  evidence: EvidenceIndex
}
```

版本规则：

1. `revision` 表示创意事实版本；`stateVersion` 表示聚合并发控制版本，二者不混用。
2. `factsRevision` 来自 Product facts snapshot；商品事实变化会使未执行的下游 revision stale。
3. `contentHash` 覆盖完整 revision；`locksHash` 只覆盖产品锁项和用户锁项。
4. Provider request、Quality evidence、Recovery capsule 必须保存所消费的 `creativeStateId + revision + contentHash`。
5. 已绑定 Provider 的 revision 永不原地修改。新动作只能派生 revision，或在已有执行记录上继续查询和对账。

### 3.2 ProductState

```ts
type ProductState = {
  productId: string
  productVersionId: string
  sku?: string
  sourceAssets: ProductSourceAsset[]
  identity: {
    productName?: string
    brandMode: 'brand' | 'generic' | 'unknown'
    brandName?: string
  }
  truth: {
    knownAttributes: Record<string, unknown>
    unknownAttributes: string[]
    userAssumptions: string[]
    sourceFactKeys: string[]
    factsRevision: number
  }
  locks: {
    immutableAttributes: Record<string, unknown>
    printLogoTextConstraints: string[]
    colorConstraints: string[]
    garmentShapeConstraints: string[]
    forbiddenChanges: string[]
  }
  license: LicenseEvidence
}
```

`ProductState` 只能引用已登记的 ProductVersion 和可追溯 source asset。未知背面、面料成分、尺寸或功能不得被写入 `knownAttributes`；用户确认的生产假设单独进入 `userAssumptions`。

### 3.3 CharacterState

```ts
type CharacterState = {
  characterId: string
  revision: number
  origin: 'OBSERVED_REFERENCE' | 'USER_CONFIRMED' | 'LIBRARY_SNAPSHOT' | 'PROPOSED'
  identity: {
    faceStructure: string[]
    hairstyle: string[]
    ageAppearance: string
    bodyProportions: string[]
    skinCharacteristics: string[]
  }
  continuity: {
    wardrobe: string[]
    behavior: string[]
    recurringTraits: string[]
  }
  allowedChanges: ('POSE' | 'EXPRESSION' | 'ACTION' | 'FRAMING')[]
  forbiddenChanges: ('FACE_REPLACEMENT' | 'BODY_CHANGE' | 'AGE_CHANGE' | 'WARDROBE_LOCK_BREAK')[]
  evidenceRefs: string[]
  constraints: string[]
}
```

Character identity is a continuity contract. It does not freeze pose, expression or action. A missing character reference remains unresolved or proposed; it is never filled with a fabricated portrait and promoted to observed identity.

### 3.4 SceneState

```ts
type SceneState = {
  sceneId: string
  revision: number
  origin: 'OBSERVED_REFERENCE' | 'USER_CONFIRMED' | 'LIBRARY_SNAPSHOT' | 'PROPOSED'
  environment: {
    location?: string
    description: string
    importantObjects: string[]
    atmosphere?: string
    timeOfDay?: string
    weather?: string
    season?: string
  }
  lighting: {
    source?: string
    direction?: string
    quality?: string
    contrast?: string
    colorTemperature?: string
  }
  continuity: string[]
  evidenceRefs: string[]
  constraints: string[]
}
```

SceneState owns the world description and lighting intent. It does not own exact per-shot placement; that belongs to SpatialState and ShotState.

### 3.5 SpatialState

SpatialState is the relationship contract between person, objects, environment and camera. It is more precise than a list of scene anchors and is required before a shot can claim spatial continuity.

```ts
type SpatialState = {
  spatialId: string
  revision: number
  coordinateSystem: 'IMAGE_NORMALIZED_2D' | 'SCREEN_SPACE_2D' | 'SCENE_RELATIVE_3D'
  anchors: Array<{
    anchorId: string
    entityId: string
    kind: 'FURNITURE' | 'OBJECT' | 'WINDOW' | 'DOOR' | 'SUBJECT' | 'CAMERA'
    position: { x?: number; y?: number; zBand?: 'FOREGROUND' | 'MIDGROUND' | 'BACKGROUND' | 'UNKNOWN' }
    orientation?: string
    dimensions?: string
  }>
  relationships: Array<{
    subjectId: string
    referenceId: string
    relation:
      | 'SITTING_ON'
      | 'STANDING_BY'
      | 'TOUCHING'
      | 'FACING'
      | 'LEFT_OF'
      | 'RIGHT_OF'
      | 'IN_FRONT_OF'
      | 'BEHIND'
      | 'OCCLUDES'
      | 'LIT_BY'
    details?: string
  }>
  subjectDepth?: string
  physicalContact: string[]
  occlusionRules: string[]
  cameraRelationship: string[]
  lightingDirection?: string
  evidenceRefs: string[]
  providerSubmissionAllowed: boolean
}
```

The current offline Spatial DNA contract maps into this model through an adapter. Its present `providerSubmissionAllowed: false` rule remains in force until a server validated package and materialized source mapping exist.

### 3.6 CameraState

```ts
type CameraState = {
  cameraId: string
  revision: number
  position?: string
  distance?: string
  height?: string
  orientation?: string
  lens: {
    focalLength?: string
    depthOfField?: string
    distortion?: string
  }
  framing: {
    shotSize?: string
    aspectRatio?: string
    subjectPlacement?: string
    headroom?: string
  }
  movement: {
    allowed: string[]
    forbidden: string[]
    stabilization?: string
    speed?: string
  }
  sceneGeometryRefs: string[]
  evidenceRefs: string[]
}
```

CameraState describes the camera in relation to the same scene and spatial anchors. A camera string inside a legacy Prompt is not sufficient to become canonical camera state; it must be parsed into a versioned adapter result or remain a legacy opaque field.

### 3.7 StoryboardState

```ts
type StoryboardState = {
  storyboardId: string
  revision: number
  campaign: {
    intent: string
    hook: string
    emotionalProgression: string[]
    productEvidence: string[]
    ctaPurpose?: string
  }
  selectedDirectionId?: string
  directionCandidates: DirectionCandidate[]
  continuityRules: string[]
  shotOrder: string[]
  packageRevisionId?: string
  sourceRefs: string[]
}
```

StoryboardState owns the creative plan and shot order. It does not own generated media, Provider attempt status, or final delivery status. Direction candidates may remain proposed; only the selected direction becomes an active input to a revision.

### 3.8 ShotState

```ts
type ShotState = {
  shotId: string
  order: number
  purpose: string
  durationSeconds?: number
  entryState?: string
  action: string
  exitState?: string
  productEvidence: string[]
  inherited: {
    productRevision: string
    characterRevision?: string
    sceneRevision?: string
    spatialRevision?: string
    cameraRevision?: string
  }
  allowedChanges: ('POSE' | 'EXPRESSION' | 'MOVEMENT' | 'FRAMING')[]
  forbiddenChanges: (
    | 'IDENTITY_DRIFT'
    | 'ENVIRONMENT_REDESIGN'
    | 'PRODUCT_REDESIGN'
    | 'LOCK_BREAK'
  )[]
  promptRefs: {
    imagePromptRevision?: string
    videoPromptRevision?: string
    preservationHash?: string
  }
  sourceBindings?: {
    selectedCandidateId?: string
    batchId?: string
    itemId?: string
    outputId?: string
    sourceSha256?: string
  }
  executionRefs?: {
    parentTaskId?: string
    variantId?: string
    attemptId?: string
  }
}
```

`sourceBindings` preserves the creative mapping from `shot_id` to selected media. `executionRefs` points to existing task execution records. The two groups must not be collapsed into one generic request JSON field.

### 3.9 QualityState

```ts
type QualityState = {
  qualificationScope: 'OFFLINE_SYNTHETIC_ONLY' | 'REAL_INPUT_UNVERIFIED' | 'PRODUCTION'
  evidence: QualityEvidence[]
  humanDecisions: HumanQualityDecision[]
  currentDecision: 'PENDING' | 'UNVERIFIED' | 'QUALIFIED' | 'REJECTED'
  qualificationScopeReason?: string
  deliveryEligibility: 'NOT_ELIGIBLE' | 'ELIGIBLE'
}
```

QualityState records evidence and human decisions associated with a CreativeStateRevision. It does not allow an AI critic, Fake/Replay result, or Provider success to write a human qualification or Deliverable state. Existing task, output and delivery contracts remain the authoritative execution and delivery owners.

## 4. Relationships and Ownership

```text
ProductVersion ──snapshot──> ProductState
                         │
                         ▼
CreativeState ──revision──> CreativeStateRevision
        │                    ├── CharacterState
        │                    ├── SceneState
        │                    ├── SpatialState
        │                    ├── CameraState
        │                    ├── StoryboardState
        │                    ├── ShotState[]
        │                    └── QualityState
        │
        ├──> CreativeStateAdapter ──> Image task / video task / Kling request
        ├──> QualityEvidenceAdapter ──> Validation / human review
        └──> Recovery/Handoff Adapter ──> existing recovery and delivery surfaces
```

Ownership rules:

| Boundary | Owns | Does not own |
| --- | --- | --- |
| Creative Layer | Product/character/scene/spatial/camera truth, direction, storyboard, shot intent, locks, evidence references, revision lineage | Provider task lifecycle, cost settlement, remote IDs, downloads, runtime retries, final delivery |
| Provider Layer | Request translation, provider capability checks, input materialization, submission ticket, remote status, UNKNOWN reconciliation, provider-specific parameters | Creative identity, package planning, human qualification, prompt re-planning |
| Quality Layer | Evidence collection, technical validation, pixel/semantic observations, human review records, failure taxonomy | Creative revision ownership, automatic qualification from AI observations, Provider submission |
| Task/Execution Layer | Existing ParentTask/Variant/Attempt/ImageBatch/Item/Output state, idempotency, quota, ledger, polling, recovery and delivery contracts | Canonical character, scene or storyboard truth |
| UI Project/Memory Layer | Project context, local composition, chronological creative memory projection and navigation | Server authority, billing, Provider state, production qualification |

### 4.1 Single write path

All canonical creative changes must pass through a domain command that:

1. checks owner and expected `stateVersion`;
2. loads the current `CreativeStateRevision`;
3. validates source facts, locks, permissions and revision dependencies;
4. creates a new immutable revision or an append-only evidence record;
5. updates only the current pointer and concurrency version;
6. emits an outbox event for read-model adapters.

Provider and Quality services may append execution/evidence records, but they cannot mutate ProductState, CharacterState, SceneState, SpatialState, CameraState or StoryboardState in place.

### 4.2 Staleness rules

The following changes make dependent creative revisions stale:

- ProductVersion facts, source hash, license or revocation changes;
- user lock changes;
- CharacterState or SceneState revision changes;
- SpatialState or CameraState changes that affect a shot;
- Storyboard shot order, purpose or selected direction changes;
- Prompt Registry or Preservation ruleset changes;
- selected candidate, approval scope or source mapping changes.

Stale means “cannot be newly bound for execution until recompiled”. It does not delete prior history or invalidate already submitted remote work.

## 5. Current-to-Canonical Migration

Migration must preserve the existing workflow and keep legacy clients working. The sequence below uses adapters and dual-read verification before any write path is changed.

### Phase 0: Freeze vocabulary and hashes

Deliver an architecture contract before implementation:

- canonical names and enum values for Product, Character, Scene, Spatial, Camera, Storyboard, Shot and Quality;
- identity of `creativeStateId`, `revision`, `stateVersion`, `factsRevision`, `contentHash` and `locksHash`;
- source/evidence status vocabulary;
- mapping rules for `FIRST_FRAME`, `SHOT_01` and later shot IDs;
- explicit distinction between creative truth, execution status, quality evidence and delivery.

No database migration or Provider change belongs in this phase.

### Phase 1: Build the read-only canonical projection

Create a pure assembler that reads current records and returns a `CreativeState` projection:

- Product/ProductVersion → ProductState;
- `CreativeTask.snapshot_json` and `CreativeRecord` → current package, facts, locks and evidence;
- frontend `CreativeIntelligenceSnapshot` / Reality contracts → Character/Scene/Camera/Spatial adapters when available;
- Director storyboard snapshot → StoryboardState and ShotState;
- image batch/item/output and existing selection records → source bindings;
- ValidationResult, quality gates and human decisions → QualityState evidence.

At this phase the projection is diagnostic and read-only. It must report missing or conflicting sources instead of silently choosing one.

### Phase 2: Canonicalize the Director package

Make the selected direction, package revision, Reality decisions, Prompt Preservation snapshot and shot mapping materialize into a `CreativeStateRevision`. Keep the current Director API response shape through an adapter.

The existing `CreativeRecord` append-only table and `CreativeTask.snapshot_json` can be the first storage implementation. Do not duplicate the same payload into an unrelated Director table.

### Phase 3: Integrate Storyboard and Shot

Move storyboard identity from positional assets and nested request JSON to explicit canonical `storyboardId`, `shotId`, order and revision fields. Preserve:

- legacy `ParentTask.assets` for existing tasks;
- `ImageGenerationBatch` / `ImageGenerationItem` / `ImageGenerationOutput` IDs;
- independent FIRST_FRAME and VIDEO_STORYBOARD qualification and selection;
- partial failure and multi-candidate history;
- existing old automatic/custom video behavior.

New Director-generated jobs must reference a canonical `ShotState`; legacy tasks receive a read-only adapter without being backfilled with invented CreativeState records.

### Phase 4: Attach Provider adapters

Generate existing `ProviderRequestContract`, `ProviderInputLeaseRecord` and `ProviderSubmissionTicketRecord` from a validated CreativeStateRevision and ShotState:

```text
CreativeStateRevision
  -> provider request adapter
  -> capability / input / authorization preflight
  -> durable lease
  -> durable submission ticket
  -> existing provider executor
```

The adapter must preserve prompt, reference order, hashes, shot mappings and execution mode. `director_fixed` must consume the locked revision and must not call legacy planning or learning functions.

### Phase 5: Attach Quality and recovery projections

Quality adapters read a revision and its outputs, then append evidence or human decisions. Recovery capsules and Creative Memory entries are derived from the same revision IDs and hashes.

AI review remains advisory. Human qualification and Deliverable status stay in the existing task/output/delivery contracts until a separate product decision changes them.

## 6. Module Impact Analysis

### 6.1 First implementation boundary

The first implementation should be a backend domain contract and pure adapters, not a page rewrite:

```text
backend/src/libtv_agent/creative/
  state.py                    # canonical value objects and invariants
  state_projection.py         # current-system -> CreativeState read projection
  state_revision.py           # immutable revision/hash helpers
  state_adapters.py           # Director/Product/Storyboard/Shot adapters
  state_commands.py           # future write command boundary
  state_evidence.py           # evidence references and provenance
```

The exact filenames are proposed and require approval. They are not an instruction to create them in this phase.

### 6.2 Existing modules to adapt

| Area | Existing files | Required future change |
| --- | --- | --- |
| Product | `domain/models.py`, `api/products.py`, `services/product_versions.py` | expose an immutable ProductState snapshot and facts revision; preserve current ProductVersion API |
| Creative workflow | `creative/workflow.py`, `services/creative_workflow.py`, `api/creative_workflow.py` | compile and validate against CreativeStateRevision; keep current offline/fake contracts during migration |
| Director frontend | `frontend/src/creative-project/*`, `frontend/src/features/director-studio/*` | read a canonical projection through selectors; keep local project and memory as projections |
| Reality | `frontend/src/creative-project/reality.ts`, `realityAdapters.ts` | map Character/Scene/Camera/Style/Reality into state components without making each a separate owner |
| Spatial | `frontend/src/features/spatial-understanding/*`, `backend/contracts/*spatial*` | adapt SpatialState to current offline contracts; preserve `providerSubmissionAllowed=false` until approved |
| Storyboard | `frontend/src/shared/components/studio/Storyboard.tsx`, Director storyboard snapshot, `domain/schemas.py` | stop deriving identity from list order; use explicit shot IDs and canonical revision references |
| Image bridge | `services/creative_image_bridge.py`, `creative_image_workflow_orchestrator.py` | consume ShotState source binding and canonical product snapshot |
| Video bridge | `services/creative_video_bridge.py`, `services/kling_preparation.py`, `fixed_video_tasks.py` | generate existing Kling input from canonical shot/reference plan; leave Provider execution unchanged |
| Provider boundary | `services/creative_provider_requests.py`, `creative_provider_preflight.py`, `creative_provider_submission*.py`, `creative/*lease*` | validate revision/hash references and translate only provider-specific fields |
| Quality | `creative/media_qualification.py`, `quality/`, `ValidationResult`, image output review API | append evidence against revision; keep human approval and delivery gates authoritative |
| Handoff/recovery | `creative/handoff.py`, `directorRecovery.ts`, `creative-project/memory*.ts` | derive manifests and memory events from revision and execution references |

### 6.3 Modules that must not become canonical

These remain execution or presentation boundaries:

- `kling_preparation.py`: Provider input preparation, not creative truth;
- `creative_provider_requests.py`: request contract, not source state;
- `ProviderSubmissionTicketRecord`: submission claim, not package revision;
- `GenerationAttempt`: remote execution state, not shot intent;
- `ImageGenerationOutput.quality_gates_json`: output evidence, not Product/Character/Scene identity;
- `CreativeProject` local store and `InMemoryCreativeMemoryAdapter`: UI projection and history, not server authority;
- legacy `ParentTask.assets` order: compatibility input, not canonical shot identity.

## 7. API and Storage Direction

The target API should expose a versioned read model before exposing mutation endpoints:

```text
GET  /api/v1/creative-states/{creative_state_id}
GET  /api/v1/creative-states/{creative_state_id}/revisions/{revision}
GET  /api/v1/creative-states/{creative_state_id}/shots/{shot_id}
```

Future mutations should be command-shaped and optimistic-concurrency protected:

```text
POST /api/v1/creative-states/{id}/commands
```

The command payload must carry `expected_state_version`, an idempotency key and one explicit action. It must not accept an arbitrary replacement `snapshot_json` from the client.

Storage options, in order of preference:

1. evolve `CreativeTask`, `CreativeRecord` and related revision records so the existing durable boundary remains the base;
2. add narrow normalized tables only where queryability or uniqueness cannot be guaranteed in JSON;
3. keep immutable JSON snapshots for the full revision and hash them;
4. do not duplicate ProductVersion, Provider tickets, task attempts or Quality decisions into CreativeState tables.

A future normalized model may use:

```text
creative_state
creative_state_revision
creative_state_evidence
creative_state_shot
creative_state_command
```

This is a later implementation option, not a request to add migrations now. Any choice must first prove it preserves current migration heads, old tasks, idempotency and production-only differences.

## 8. Boundary and Compatibility Rules

### Creative Layer

Owns:

- creative truth and source facts;
- Product/Character/Scene/Spatial/Camera identity;
- direction candidates and selected direction;
- storyboard intent, shot order and continuity;
- allowed/forbidden changes;
- immutable package and revision lineage;
- evidence references and provenance.

May request:

- image/video generation through adapters;
- quality observations;
- recovery and handoff projections.

Must never:

- choose a Provider silently;
- create a paid attempt;
- mark a candidate human qualified from AI output;
- rewrite an already bound revision.

### Provider Layer

Owns:

- provider/model parameters;
- capability and request validation;
- materialization and ordered reference bindings;
- submission ticket, lease and idempotency;
- remote status, UNKNOWN reconciliation and provider error mapping.

Must consume:

- canonical revision ID/hash;
- explicit shot ID;
- canonical Product reference;
- locked Prompt and Preservation hash;
- authorized reference manifest.

Must not:

- infer or rewrite character identity;
- invent scene or camera rules;
- regenerate the storyboard;
- use provider success as quality approval.

### Quality Layer

Owns:

- technical validation;
- evidence and pixel observation;
- structured findings and failure taxonomy;
- human review records and qualification decisions.

Must preserve:

- evidence scope (`OFFLINE_SYNTHETIC_ONLY`, real input unverified, production);
- source revision and output hashes;
- distinction between AI recommendation, human qualification and Deliverable.

## 9. Implementation Roadmap

| Phase | Deliverable | Exit criteria |
| --- | --- | --- |
| Phase 1: State model | Canonical value objects, revision/hash rules, ownership contract, read-only projection | One fixture can reconstruct Product, Director package, Storyboard, Shot, Provider references and Quality evidence without conflicting sources |
| Phase 2: Storyboard integration | Explicit storyboard/shot IDs, direction/package selection and shot inheritance | FIRST_FRAME and SHOT_01 retain independent selection, review, order and source mapping; legacy tasks still load |
| Phase 3: Generation integration | Image/video adapters consume a validated revision | Existing image/video request shapes, idempotency, unknown submission and old modes remain unchanged |
| Phase 4: Kling integration | Kling adapter derives references and parameters from ShotState | Provider limits, reference order, materialization and `director_fixed` negative assertions pass |
| Phase 5: Quality validation | Quality evidence and human review projections bind to revision/output hashes | AI evidence cannot write QUALIFIED; human review and delivery semantics remain separate |

Recommended implementation order inside Phase 1:

1. Define `CreativeStateRevision` and hash invariants.
2. Define ProductState adapter from ProductVersion.
3. Define Director package and Reality adapter.
4. Define Storyboard/Shot source mapping adapter.
5. Define read-only Quality and Provider projections.
6. Add conflict diagnostics and fixture coverage.

## 10. Migration Acceptance Gates

Before implementing the foundation, the following decisions require human acceptance:

- whether `CreativeTask` remains the aggregate root or becomes a compatibility facade over `CreativeState`;
- whether Character/Scene/Spatial/Camera are persisted as full snapshots, references plus snapshots, or references only for the first release;
- the authoritative `shot_id` namespace beyond `FIRST_FRAME` and `SHOT_01`;
- whether a package revision is itself a CreativeStateRevision or a child artifact of one;
- the exact qualification scopes that can be represented by QualityState;
- the production bridge approval required before any Provider adapter is allowed to consume a real revision.

Engineering can prepare read-only projections and conflict reports after the architecture is accepted. Code implementation, schema migration and real Provider use remain a later phase.

## 11. Risks and Non-Goals

Risks:

- treating an offline frontend snapshot as server truth;
- copying the complete creative state into every Provider request;
- allowing Prompt or shot order to become an implicit identity;
- conflating `stateVersion`, `revision`, `factsRevision`, output revision and Provider attempt revision;
- backfilling old tasks with invented Character/Scene/Spatial facts;
- allowing AI Quality observations to mutate human qualification.

Non-goals:

- replacing the existing React/TypeScript/Vite stack;
- rewriting the current image/video execution pipeline;
- creating a second agent system;
- adding ComfyUI or new models;
- changing Kling execution logic in this architecture phase;
- enabling live Provider calls, paid generation, migrations, deployment or service restart.

## 12. Approval Outcome

This document should be reviewed as the gate before the next implementation task. The next authorized task, after approval, should be:

```text
Implement CreativeState Foundation
```

That task should begin with a read-only `CreativeState` projection and invariant tests. It should not begin by replacing existing task tables, Provider adapters or frontend state stores.
