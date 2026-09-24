# UI Upgrade PM Execution Board

Baseline: 2026-09-24, testing `9dc6b5c`, production checkout
`C:/Users/Reel/Documents/libtv-auto-main-sync`, main `47b93db`.
Production URL: http://192.168.30.126:5173/.

## Ownership And Scope

User correction, 2026-09-24: this task owns frontend pages, layout, navigation,
interaction, accessibility, responsive behavior and frontend acceptance only.
Backend security, callback policy and G1 belong to task
`01a0cdb7-c7c6-7840-ab2f-0c932e004dc2` (分阶段执行衣影工坊增强计划).
The user has already decided callback policy there. Do not request that decision
again, implement a competing policy, edit its execution board, or change backend
routes, schemas, billing, migrations or provider behavior in this UI task.
The thread lookup confirmed active status but returned no decision text; do not
infer the chosen policy. Backend-dependent UI work waits for confirmed API contracts,
while independent frontend work proceeds. UI approvals do not waive G1 deployment gates.

The parent agent owns prioritization, assignment, integration, evidence review,
acceptance and scoped promotion. Routine implementation choices are delegated;
billing policy, authorization boundaries, destructive migration and external
integration compatibility require user decisions. Source promotion is not live
deployment. Never copy secrets, runtime state or real environment files.

Use bounded briefs with file ownership and acceptance cases. Prefer mini/high for
read-only audits, medium reasoning for isolated UI work, and high reasoning for
concurrency or paid-submission contracts. Avoid full-history delegation and repeated
reads. Child completion reports are not sufficient acceptance evidence.

Delegation transport failed during this PM intake: two auditors reported empty
payloads, including one follow-up attempt. No audit evidence is credited to these
calls. Suspend additional dispatch until message delivery is confirmed; parent
performed the release-gate review directly.

## Work Packages

| ID | Package | State | Acceptance evidence |
| --- | --- | --- | --- |
| U00 | Recovery query and UI primitives | Foundation only | Previous tests/build; components not yet integrated into business pages |
| U01 | Safe storage and account isolation | Open, high priority | Blocked storage, logout/account switch, no cross-user IndexedDB draft recovery |
| U02 | Frontend batch progress/recovery presentation | Backend manifest is an external dependency | Consume confirmed server contracts; never infer safe retry or duplicate server implementation |
| U03 | Unknown reconciliation and quota presentation | Open; release depends on G1 | Server-authoritative result; no unknown resubmission; no invented supplier price |
| U04 | Selection/review separation | Single-output workflow verified on testing; bulk review open | Selection never approves; explicit review and reject reason; video transfer only qualified outputs |
| U05 | Records deep links and bounded lists | Open | Back/forward/detail return, matching counts, pagination, no sensitive URL data |
| U06 | Compare/review/delivery/library | Open; contract discovery required | Side-by-side/overlay, traceable decisions, actual version/reference data rather than fabricated metadata |
| U07 | Shared component integration and visual unification | Open | Existing business pages migrated; coherent status semantics, errors and permission states |
| U08 | Browser and performance acceptance | Not run | 1440/1024/768/390, keyboard/reduced motion, synthetic media, 50/200/1000 records |

Dependency order: U01/U04/U05/U07 independent frontend increments; U02/U03 when
backend contracts are available; U06 and U08. Test changes in isolated fixtures. Incrementally promote
only verified source patches, preserving production-specific behavior. Do not infer
brand/workspace roles from cosmetic navigation or invent billing rules.

## Verified Intake Findings

- G1 findings are owned by the other task. The initial intake incorrectly treated
  its historical decision record as a new UI decision request; that request is withdrawn.
- `frontend/src/imageCenterStore.ts` uses a shared `active` draft key.
- `frontend/src/ImageCenter.tsx:toggleOutput` still writes QUALIFIED when selecting.
- The regenerate button is rendered without an unknown-result guard.

## Decision D01: Withdrawn From UI Scope

Callback compatibility is already handled in the other task per the user.
No callback code was changed during this PM intake. No duplicate approval or
implementation is required here. Any future frontend dependency is tracked by
its required API contract, not by reopening the backend policy decision.

## Acceptance Rules

Track implementation, automated tests, browser evidence, main promotion and live
deployment separately. Passing static markup tests is not keyboard/browser proof.
Test-branch/main test counts may differ; report each independently. No package is
complete solely because a document or unused component exists. Main is maintained
in a separate checkout; inspect its actual Git directory and HEAD before syncing,
not the stale main ref/worktree metadata in the testing repository.

## Frontend Increment: Explicit Image Review

Testing commits `bfc85a8`, `c6138e2`; main compatibility promotion `478e4ca`.
Selection no longer performs approval on testing. Explicit single-image review uses
a native drawer, two quality checks for approval, a required rejection reason,
server-returned status, preserved input on failure and an uncertain-write warning.
The uncertain-write guard is local to the open drawer, not durable reconciliation;
cross-close/reopen recovery remains an open dependency and is not accepted here.

Production lacks the quality-decision endpoint and output review fields. Only
frontend compatibility types/client were added; production cards keep review
disabled and preserve their existing selection/video workflow. No backend endpoint,
schema or policy was promoted. Enabling production review requires the other task's
contract followed by a UI integration pass; this is not a released review feature.

Evidence: 166 testing / 163 main frontend tests passed, both builds passed, testing
lint passed. The isolated `scripts/ui-image-review-check.mjs` mounts the real image
page with synthetic bitmap media and intercepts all API calls. It verifies selection
causes zero approval writes, rejection requires a reason and persists the supplied
reason, Escape restores focus, and no document overflow at 1440/1024/768/390.
Screenshots and JSON are external under the current UI task's `ui-review` evidence
directory; the 390px review screenshot was inspected. This is not whole-app visual
acceptance or proof of bulk review, partial failure or server concurrency behavior.
No live API, paid provider call, production restart or real media was used.
