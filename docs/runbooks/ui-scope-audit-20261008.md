# UI Scope Audit: 2026-10-08

## Checked Baseline

- Testing checkout: `E:/Projects/libtv自动化生成`, branch `codex/testing`,
  HEAD `3b22f3d5f932aa162fc8b15491f92ca567ceea27`.
- Main checkout: `C:/Users/Reel/Documents/libtv-auto-main-sync`, branch `main`,
  HEAD `82ccb1de9133ba621bdd68b525dfe343f844c2d3`.
- Intake status: only the user's testing ZIP was untracked; main was clean.
  The ZIP is preserved and is not part of promotion.
- Compared actual checkout files, not stale cross-repository branch refs.
  ImageCenter and the original review script/matrix matched ignoring line endings.
  No backend or production-specific behavior is changed by this audit.

## Historical Evidence Limits

Evidence root: `C:/Users/Reel/Documents/libtv-ui-review-evidence-20261008`.
Both `testing/result.json` and `main/result.json` report selection writes 0,
explicit rejection write 1, required reason, two read-only comparison panels,
Escape/focus restoration and four widths with no page errors.

The checked script closes comparison BEFORE the four result-page screenshots.
Thus these screenshots do not prove comparison responsiveness. They show one
local IndexedDB task and two identical synthetic portrait images, not server
recovery, real authorization, bulk review, all media ratios or all pages.
The old JSON has no source hash, timestamp or browser version; its matching
assertions do not independently establish which checkout revision produced it.
API responses are mocked. Main fixture success is not live production success.

Visual inspection of historical screenshots also shows the fixed selection
toolbar covering some content at narrow widths. This is not horizontal overflow;
safe areas, scroll reachability and keyboard behavior remain separate gates.

## Implementation Versus Acceptance

| Scope | Implemented | Not yet accepted / real gap |
| --- | --- | --- |
| UNKNOWN image query | Uses preserved clientBatchId to locate and merge the original batch; regeneration is guarded | Do not redo this work; it does not discover history after local identity is lost |
| S03 device/cache recovery | Account-scoped IndexedDB and known-ID batch reads | No history-discovery path or reconstruction from an empty local task set; server contract dependency |
| S06 quota | Backend per-user daily limit and concurrency guard; rejection carries limit/used/requested/remaining | No pre-submit quota display; local submission appends tasks and clears selection before rejection. Materials/config surviving does not prove an unchanged draft |
| I05 comparison | Two read-only panels, contain images, narrow-width stacking, Escape/focus return | Overlay/opacity and linked zoom/pan/reset absent |
| U08 browser/performance | Isolated image review interaction evidence | Whole-app four-width/state matrix, full keyboard/a11y, 200% zoom, 50/200/1000 records and resource lifecycle not accepted |

Source anchors: `frontend/src/features/image-center/ImageCenter.tsx`
(`mergeBatchIntoTasks`, draft-load effect, `submitTaskSet`,
`recoverUncertainTask`, `ImageOutputCompare`); `frontend/src/imageCenterStore.ts`;
`frontend/src/api.ts`; `backend/src/libtv_agent/api/image_generations.py`;
`backend/tests/test_image_quota_concurrency.py`.
The backend checks are source review only; no backend tests or live calls were
performed for this audit. Do not extend per-user quota proof to shared budgets.

`scripts/ui-smoke.mjs` uses a generic records `.page-view` selector and checks
existence, not visibility. Hidden mounted pages may satisfy it. Route smoke
therefore cannot close visual or performance gates; durationMs is not first paint.
The historical PM board's U08 "Not run" is stale relative to local image evidence,
but changing that to "complete" would also be incorrect.

## Zero-Paid Follow-Up And Handoff

The review script now captures open comparison at 1440/1024/768/390, waits for
drawer animations, decodes both images, checks contain and stable horizontal
geometry, verifies zero review writes and focus return at each width, and checks
that the second panel metadata can be scrolled into the viewport.
External HTTP requests are blocked and API calls mocked; no live login occurs.
JSON records source HEAD, script SHA256, browser version and capture time.
The tested HEAD is the base revision; the script hash identifies the working
script increment. This remains an image-only fixture, not an application rollout.

Follow-up evidence is external at `comparison-followup/testing` and
`comparison-followup/main` under the evidence root. Original evidence is retained.
Frontend unit suites are run separately for each checkout; no build is run,
so build acceptance is not renewed and generated production files are untouched.

Two bounded read-only agents audited recovery/quota and comparison/performance.
Parent checked their key claims against source and existing evidence before
recording them here; agent completion itself is not browser acceptance.
Next independent batch: synthetic, offline fixtures for composer, records,
library, settings and authorized admin views, with specific visible-route
assertions. Measure large-list performance separately with declared fixture sizes
and stopping limits. Recovery/quota UI waits for confirmed server contracts;
no backend, billing or authorization policy is invented in this frontend audit.
