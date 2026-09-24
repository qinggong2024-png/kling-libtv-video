# UI Upgrade Acceptance Matrix

Baseline: review supplement dated 2026-09-24. This matrix is a release gate,
not a claim that every proposed feature has been implemented.

## Environments And Evidence

- Implement and validate on `codex/testing`, then promote the scoped source
  changes to `main`, preserving production-only behavior.
- Production is `http://192.168.30.126:5173/`. Localhost is not production.
- Run mutation, fault-injection, concurrency, and paid-operation tests against
  isolated fixtures with fake providers. Production smoke checks are read-only.
- Never include credentials, prompts, original media, provider URLs, or live
  account data in screenshots, logs, fixtures, or committed reports.
- Existing test names below identify useful regression coverage. They do not
  prove new UI workflows or server contracts are implemented.

## Safety And Recovery Gates

| ID | Scenario | Required assertion | Existing regression anchor | Additional evidence required |
| --- | --- | --- | --- | --- |
| S01 | Same group submitted twice or from two tabs | Exactly one task and one charge; stable idempotency key | `test_stale_idempotency_claims.py`, `test_image_submission_race.py` | Two-tab browser test and manifest version conflict test |
| S02 | Groups 1/2 succeed, 3 fails, 4 is unknown | Resume only confirmed failed groups; never resubmit unknown automatically | `batchUpload.test.ts`, `test_image_generation_batches.py` | End-to-end partial submission fixture |
| S03 | Clear site data, reopen browser, or switch device | Authorized server batch state restores without relying on local cache | None identified for full workflow | Recovery API integration test and browser test |
| S04 | Timeout, disconnected response, or malformed response after creation | Queryable reconciliation record; no inferred failure | `test_paid_acceptance_safety.py`, `test_launch_started_recovery.py` | Fault injection at every response boundary |
| S05 | User queries unknown result; administrator classifies it | Role-checked classification, audit trail, bounded escalation | `test_action_gating.py`, `test_user_management.py` | Reconciliation endpoint permission and audit assertions |
| S06 | Two users reserve the last available quota | At most one accepted request; no new batch or cleared draft for rejected request | `test_image_quota_concurrency.py`, `test_image_quota.py` | UI draft preservation and cost preview assertions |
| S07 | Retry failed output or failed download | Server identifies billable retry; download-only recovery never regenerates | `test_materialization_lifecycle.py`, `test_success_path_settlement.py` | Incremental cost confirmation and reservation settlement tests |
| S08 | Expired session, revoked membership, direct administrator link | No privileged action; reauthorization before accessing media or shared detail | `test_shared_auth_and_logging.py`, `test_user_management.py` | Browser route and permission-change tests |
| S09 | Logout, workspace switch, or blocked browser storage | Sensitive local state cleared or isolated; memory fallback remains usable | None identified for full workflow | Storage adapter unit tests and account-switch browser test |
| S10 | Provider paused, rate limited, unavailable, or incompatible | Typed retry policy; no silent model/price change; existing tasks retained | `providerPresentation.test.ts`, `test_runtime_control.py` | Provider capability and fallback confirmation tests |

## Interaction And Accessibility Gates

| ID | Scenario | Required assertion |
| --- | --- | --- |
| I01 | Empty, malformed, duplicate, oversized, single-group and multi-group upload | Correct scoped validation; valid groups and user settings retained |
| I02 | Global settings, group override, reset, refresh, navigation away | Stable identity and explicit restoration; no duplicate submission |
| I03 | Selection, approval, rejection, bulk review, and correction | Selection is independent from approval and delivery; rejection reason and actor recorded |
| I04 | Filters, search, pagination, copied URL, detail return, back/forward | Same authorized result set; restore selection and scroll where valid; no sensitive URL fields |
| I05 | Side-by-side and overlay review | Linked zoom works; source image remains inspectable without mandatory crop |
| I06 | Keyboard-only upload result filtering and review | Predictable Tab order; named icon controls; Escape closes preview; focus returns to opener |
| I07 | Loading, slow network, partial/full failure, unknown, forbidden, expired session | Core pages expose every applicable state without losing drafts or concealing failure |
| I08 | Hidden tab, offline network, expired session, then recovery | Polling backs off or pauses and resumes safely without a request burst |

## Visual And Performance Gates

Capture video composer, image center, records, library, settings, and authorized
operations pages at widths 1440, 1024, 768, and 390 CSS pixels. Include long
Chinese titles, filenames and error codes; empty results; and loading/error
states. Use synthetic fixtures rather than customer data.

- Check overlap, horizontal overflow, fixed toolbar safe areas, and on-screen
  keyboard behavior. Verify browser zoom at 200% and enlarged system fonts.
- Automate text contrast checks; inspect high-contrast mode, accessible names,
  status live regions, and reduced-motion behavior.
- Use fixed media container dimensions; review images use `contain`; inspect
  portrait, landscape, and square assets for clipping and layout shifts.
- Measure first paint, filtering, scroll responsiveness and memory at 50, 200,
  and 1000 records. Record device/browser and fixture size with measurements.
- Repeatedly open and close previews; verify object URLs, video elements, and
  Blob references do not grow without bound.
- Existing `scripts/ui-smoke.mjs` provides route smoke coverage. A passing route
  smoke run alone is not a visual, accessibility, or performance acceptance.

## Release Checklist

1. Record implemented scope, explicitly deferred items, and compatibility needs.
2. Run focused regression tests plus the complete frontend test/build checks.
3. Attach isolated backend integration and browser evidence for affected gates.
4. Document feature flag defaults, cohort scope, and rollback procedure.
5. Compare test and production branches; promote only relevant source, safe
   configuration examples, tests, and documentation. Never promote real `.env`,
   secrets, runtime state, caches, or generated artifacts.
6. Verify both worktrees, run safe production checks, and report synchronization
   separately from application-process reload and full product acceptance.
