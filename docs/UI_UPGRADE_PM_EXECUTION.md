# UI Upgrade PM Execution Board

Baseline: 2026-09-24, testing `9dc6b5c`, production checkout
`C:/Users/Reel/Documents/libtv-auto-main-sync`, main `47b93db`.
Production URL: http://192.168.30.126:5173/.

## Ownership And Scope

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
| U02 | Server batch manifest and stable submission identities | Open, high priority | Two tabs, response loss, partial success, refresh/site data deletion; no extra create or charge |
| U03 | Unknown reconciliation and quota presentation | Open; release depends on G1 | Server-authoritative result; no unknown resubmission; no invented supplier price |
| U04 | Selection/review separation | Open | Selection never approves; explicit review and reject reason; video transfer only qualified outputs |
| U05 | Records deep links and bounded lists | Open | Back/forward/detail return, matching counts, pagination, no sensitive URL data |
| U06 | Compare/review/delivery/library | Open; contract discovery required | Side-by-side/overlay, traceable decisions, actual version/reference data rather than fabricated metadata |
| U07 | Shared component integration and visual unification | Open | Existing business pages migrated; coherent status semantics, errors and permission states |
| U08 | Browser and performance acceptance | Not run | 1440/1024/768/390, keyboard/reduced motion, synthetic media, 50/200/1000 records |

Dependency order: confirm G1 release policy; U01/U02 safety groundwork; U03/U04/U05;
U06/U07; U08. Test independent changes in isolated fixtures. Incrementally promote
only verified source patches, preserving production-specific behavior. Do not infer
brand/workspace roles from cosmetic navigation or invent billing rules.

## Verified Intake Findings

- `docs/G1_SECURITY_ACCEPTANCE_20260924.md` explicitly says G1 is incomplete and
  not to enter G2. `docs/G1_PM_EXECUTION.md` records an unresolved callback decision.
- `api/kling.py:receive_kling_callback` has no actor/source authentication dependency
  before calling the callback service. Provider re-query does not authenticate the
  sender. This is a compatibility/security policy decision, not a UI color choice.
- `frontend/src/imageCenterStore.ts` uses a shared `active` draft key.
- `frontend/src/ImageCenter.tsx:toggleOutput` still writes QUALIFIED when selecting.
- The regenerate button is rendered without an unknown-result guard.

## Decision D01: Callback Compatibility

Awaiting user approval. Recommended temporary policy: reject unauthenticated
callbacks by default, retain provider-bound polling of existing tasks, and never
resubmit or free uncertain charges. Before deployment prove polling coverage and
callback/poll race behavior with isolated providers. Do not invent vendor headers.

Approval authorizes implementation and isolated verification, not production
restart, paid calls, destructive migration or bypass of remaining G1 acceptance.
An authenticated gateway with a confirmed deployment contract is an alternative
requiring supplied specifications. No callback behavior was changed at PM intake.

## Acceptance Rules

Track implementation, automated tests, browser evidence, main promotion and live
deployment separately. Passing static markup tests is not keyboard/browser proof.
Test-branch/main test counts may differ; report each independently. No package is
complete solely because a document or unused component exists. Main is maintained
in a separate checkout; inspect its actual Git directory and HEAD before syncing,
not the stale main ref/worktree metadata in the testing repository.
