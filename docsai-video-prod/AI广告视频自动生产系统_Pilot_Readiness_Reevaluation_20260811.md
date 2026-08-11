# AI 广告视频自动生产系统 Pilot Readiness Re-evaluation

- Previous checkpoint: `AI-VIDEO-PROD-20260810-2000`
- Evaluation date: `2026-08-11` (Asia/Shanghai)
- Gate result: `PASS_WITH_GUARDRAILS`
- State: `PARTIAL / BUSINESS GATES FUNCTIONALLY VERIFIED / REAL ASSEMBLY EXECUTION VERIFIED / PILOT REQUIRES HUMAN GATES`

## Phase 1 — Freeze Current Implementation

```text
IMPLEMENTATION_REVISION
Git revision: 77b38082301fe408961e19ca9c9d2188fa65fc20
Runtime content revision: ddd8db142a419c849c31fdc2ac7ce1a35d935898f2f8168b7f19588076c7f58b
Branch: codex/testing

WORKTREE_STATUS
Tracked tree: CLEAN at implementation freeze
Untracked, excluded: AI_VIDEO_PROD_20260810_1712_PATCHED_PACKAGE.zip
Untracked, excluded: AI_VIDEO_PROD_20260810_1712_PATCHED_PACKAGE/
Ignored, excluded: var/** runtime databases, logs, artifacts, provider credentials, generated evidence

INCLUDED_PATCHES
- Production delivery qualification and required final human gates
- Qualified generated-image provenance carried into video assets
- Deployment source/schema/config/runtime revision evidence
- Merge of the published production provider line into the validated gate line
- Bach provider, runner reload, media download, restore, and configuration-aware technical validation fixes
- Isolated Full-profile Bach provider selection and readiness checks

EXCLUDED_LOCAL_ARTIFACTS
- Formal production .env and runtime secrets
- Local encrypted provider configurations under var/**
- Generated databases, logs, reports, frames, video outputs, and frontend build artifacts
- Unrelated uncommitted advanced motion-action catalog changes in the formal worktree
```

The formal `5173` worktree was not modified. It remains `main@37ae849bcd25a1023555c85c94087cd39ff2c526` with 11 pre-existing dirty files.

## Phase 2 — Runtime Revision Drift

### Formal runtime (read-only observation)

- URL: `http://192.168.30.126:5173/`
- sourceRevision: `3422174e7c731a4c4f00e2ae0b15badd14aa3b64514794530ade9b9decc8f63d`
- Runtime mode: `development / real / live`
- Provider: `bach / bach-1.0`
- Formal runtime was not restarted, migrated, or modified.

### Production-equivalent validation runtime

- URL: `http://127.0.0.1:5175/` (`8001` API)
- Git implementation revision: `77b38082301fe408961e19ca9c9d2188fa65fc20`
- runtime sourceRevision: `ddd8db142a419c849c31fdc2ac7ce1a35d935898f2f8168b7f19588076c7f58b`
- validated content revision: `ddd8db142a419c849c31fdc2ac7ce1a35d935898f2f8168b7f19588076c7f58b`
- schemaRevision: `b7d9e1f3a502`
- configRevision: `b3fdd760e6a8b91f056ff4343bb286a787fba087fdd4972b383052a817275681`
- runtimeVersion: `0.1.0`
- mode: `development / real / live / paid authorized`
- provider: `bach / bach-1.0 / authenticated`
- runner: `ONLINE`
- readiness: database and schema `OK`

Result: runtime `sourceRevision == validated content revision` is proven on the isolated production-equivalent path. Formal production drift is isolated rather than changed in place.

## Phase 3 — Production-equivalent Editing / Assembly E2E

### Input and binding evidence

| Role | ID | SHA-256 | Bound/used |
|---|---|---|---|
| Storyboard 1 | upload `e2b651b6-95bb-4cb6-8dd4-951d19ffbeea`; asset `3af98c40-dbaf-4f1e-b2e7-cc4a45db5d7e` | `c7a496def10cafdb0e5aa12ba69ad048d81952ad467ce065f9ecea6abf5bbaa6` | required, `usedForGeneration=true` |
| Storyboard 2 | upload `3fefaef9-2320-45cd-ad1c-a96909488e13`; asset `8668e638-f5f4-48b5-9cc7-2b0d58f60304` | `4123fb9e7e20b80d2c81f15221573338b80b8e3aa6d45d9627f4d574cc7f3111` | required, `usedForGeneration=true` |
| Exclusion control | upload `ebb61072-e813-427c-84f9-d637c79ac54b` | `392f099e6e0da579541d495aa53783bd6559033f05daf3824a7b0f1053e448a5` | not bound; `claimed_task_id=null` |

The task asset table contains exactly the two storyboard assets. The visually distinct exclusion-control image is absent from task assets and output frames. It is an exclusion control, not a fabricated system `REJECTED` decision.

### Execution evidence

- task: `2997c7e8-f7f5-48cf-8dd3-f32f0b34023a`
- variant: `945bb45c-20e0-4e28-9c41-e8196667bcdc`
- attempt: `e881ef18-a696-4ba5-af8c-668b65566be8`
- command: `a7844ed5-63b0-46e1-815f-8d234bb7ba09`
- provider task: `ee93daaaa99447aebd208b49e1b3f173`
- provider/model: `bach / bach-1.0`
- execution backend: `BACH_API`
- intent hash: `8cef09aa8c5dd318c1774d8e00f9890f3d717dc776dd6f357a158b648778e05c`
- submitted: `2026-08-11T03:03:56.916992Z`
- completed: `2026-08-11T03:06:29.173080Z`
- generation duration recorded by task: `152.3s`
- command terminal status: `TERMINAL`
- attempt status: `SUCCEEDED`

This is a real paid provider execution, not a mock or function-only test.

### Output and technical evidence

- output artifact: `41c1fbb0-35c8-41d9-95ba-4f7be43f7252`
- SHA-256: `a703639ed7c5d8ac3ada0fa64973e939ea05c9b62a34b538c9b38315992379c9`
- size: `4,733,812 bytes`
- duration: `6.01s`
- resolution: `1080x1920` (`9:16`)
- video: `H.264 High`, 24 fps, 144 frames
- audio: `AAC LC`, 48 kHz stereo
- object-store SHA equals runner-download SHA
- `ffprobe` container probe: PASS
- full `ffmpeg` decode to null sink: PASS
- persisted technical validation: `PASSED`, rule `1.0.0`, no issue codes
- final state: `AWAITING_FINAL_APPROVAL`
- final approval: `PENDING`

Local evidence:

- `var/test-live/runner/downloads/2997c7e8-f7f5-48cf-8dd3-f32f0b34023a/2026-08-11_00000000_2997c7e8_result-1_v1.mp4`
- `var/test-live/evidence/assembly-e2e-1786417412/`
- `var/reports/provider-merge-targeted.xml`
- `var/reports/pytest-junit.xml`

No final approval was fabricated. AI frame inspection is supporting evidence only and is not human Ground Truth.

## Verification / Baseline

- Targeted provider/runner/media/batch regression: `29 passed`
- Backend full suite: `390 passed, 2 skipped, 0 failed`
- Skips: explicitly isolated PostgreSQL/MinIO online-infrastructure tests
- Ruff lint/format: PASS
- Alembic offline SQL: PASS
- Alembic fresh SQLite migration through `b7d9e1f3a502`: PASS
- Frontend lint: PASS
- Frontend tests: `21 files / 154 tests` PASS
- Frontend build: PASS

## REAL_BATCH_PILOT_READINESS_GATE

```text
RESULT = PASS_WITH_GUARDRAILS

Scope
Production-equivalent single-variant two-frame Bach assembly, download, decode,
technical validation, revision evidence, and enforcement of the final human gate.

Evidence
Real BACH_API attempt and provider task, exact input bindings/hashes, exact output
artifact/hash, full decode, schema/config/source/runtime revisions, full repository checks.

Remaining Gaps
- This E2E used real direct-upload storyboard assets; it did not create a new
  system ImageGenerationOutput with persisted QUALIFIED/REJECTED Ground Truth.
- Final product-fidelity and human-critical approval remains PENDING by design.
- Formal 5173 still runs sourceRevision 3422174e... and must not be used for this pilot.
- Provider billing reported no exact credit count, so the reservation settled as UNKNOWN.

Guardrails
- Run the pilot only on the isolated Full path whose sourceRevision is
  ddd8db142a419c849c31fdc2ac7ce1a35d935898f2f8168b7f19588076c7f58b,
  or deploy that exact content revision to a separately approved pilot environment.
- Every required input generated by the system must have persisted QUALIFIED Ground Truth.
- Persist REJECTED decisions and prove rejected output IDs are absent from task asset bindings.
- Every output must remain non-deliverable until a human records all required final gates.
- Stop paid submissions on revision/config/schema mismatch or provider/billing uncertainty.

Runtime Revision
Git implementation 77b38082301fe408961e19ca9c9d2188fa65fc20;
runtime content ddd8db142a419c849c31fdc2ac7ce1a35d935898f2f8168b7f19588076c7f58b.

Migration Status
PASS at b7d9e1f3a502 on the isolated pilot database.

Assembly E2E Result
PASS for real Bach execution, exact asset binding, output generation, download,
hashing, decode, and technical validation. Final human delivery gate remains pending.

Baseline Status
PASS_WITH_SKIPS: 390 backend passed / 2 isolated online skips;
154 frontend passed; lint, build, and migrations passed.

Required Human Gates
Input qualification Ground Truth for generated assets; final PRODUCT_FIDELITY and
HUMAN_CRITICAL review; explicit final approval with reviewer identity/time/notes.

Next Action
Prepare a guarded real-batch pilot on the exact isolated runtime revision, obtain
human Ground Truth for required input and final gates, and do not use formal 5173
until its deployment is separately approved and revision-aligned.
```

## Phase 5 — CONTRACT_GAP

Final search covered the current repository, the formal production worktree, and `F:\download`.

| Contract | Result | Classification for current objective |
|---|---|---|
| L1 Product & Scope Contract | No standalone body located | `GUARDED` |
| L2 Production Contract | No standalone body located | `GUARDED` |
| L3 Domain Model + System Architecture Contract | No standalone body located | `GUARDED` |

Reason: L4 v1.3, Master Prompt v1.1, executable schemas/state machines, code, migration history, and current acceptance evidence were sufficient to resolve the two scoped blockers without inventing L1–L3. Their absence forbids broader product/scope/architecture reinterpretation and stronger production-wide claims, but it does not invalidate this isolated revision and assembly proof.

Located canonical/supporting contracts:

- `docsai-video-prod/AI广告视频自动生产系统_Production_Acceptance_Contract_v1.3_业务闭环修补版.md`
- `docsai-video-prod/AI广告视频自动生产系统_Codex_Master_Execution_Prompt_v1.1_修补版.md`
- `F:\download\UAP-AE_2.1_AE-DUALAXIS-EVENTGATE-CONTEXTCONTINUITY-20260810_CANONICAL_FROZEN.md`
- Historical UAP-AE/2.0 also exists, but project governance declares UAP-AE/2.1 canonical/frozen.

No L1–L3 text was recreated.
