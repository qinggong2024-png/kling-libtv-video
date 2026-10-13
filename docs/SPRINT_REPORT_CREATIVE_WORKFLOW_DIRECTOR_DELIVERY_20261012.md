# Sprint Report: Creative Workflow Director Delivery Acceptance

Date: 2026-10-12
Branch: `codex/testing`
Scope: Director handoff persistence, reload recovery, and isolated offline browser acceptance

## Completion

Completed the post-reload `director_fixed` preparation path for the single-shot offline Director workflow.

After a full page reload, Video Studio can reconstruct the read-only preparation summary from JSON-safe project metadata even when browser `File` state and the first-frame handoff are unavailable.

## Changes

- Persisted `directorFixed` metadata with the Director task id, SHOT_01 package and revision, selected candidate, source image identifier, storyboard state, and shot mapping.
- Made the fixed preparation reader accept a complete persisted `directorFixed` record when `handoff` is `null`.
- Preserved the existing priority for SHOT_01 package and revision over the legacy FIRST_FRAME handoff.
- Accepted non-empty offline source image identifiers such as `source-image-hash-1`; output image hashes remain strict 64-character hexadecimal values.
- Added selector, localStorage round-trip, no-File reload, and offline source identifier tests.
- Kept `OFFLINE_SYNTHETIC_ONLY`, `providerSubmissionAllowed=false`, and `deliverableEligible=false`.
- Did not change backend APIs, database models, migrations, Provider submission, production writes, or the browser acceptance script.

## Tests

Testing worktree `E:\Projects\libtv自动化生成`:

- Targeted Director tests: 10 passed.
- Full Vitest: 52 files, 322 tests passed.
- `npm run build`: passed.
- `npm run lint`: passed.
- Browser evidence: `E:\Codex\creative-acceptance-20261012\director-delivery-testing-final`.
- Desktop `1440x900`: passed.
- Mobile `390x844`: passed.
- Invalid recovery cleanup: passed.
- Network failure retention: passed.
- External requests: none.
- Forbidden upload, video-task, and submission-recovery writes: none.

Production worktree `C:\Users\Reel\Documents\libtv-auto-main-sync`:

- Full Vitest: 53 files, 317 tests passed.
- `npm run build`: passed.
- `npm run lint`: passed.
- Browser evidence: `E:\Codex\creative-acceptance-20261012\director-delivery-main-final`.
- Desktop `1440x900`: passed.
- Mobile `390x844`: passed.
- Invalid recovery cleanup: passed.
- Network failure retention: passed.
- External requests: none.
- Forbidden upload, video-task, and submission-recovery writes: none.

## Findings

The browser acceptance initially found three frontend recovery defects: missing storyboard metadata in the persisted planning snapshot, a reload path that required the File-dependent handoff, and strict SHA parsing of the offline source identifier. All three were fixed and revalidated on both worktrees.

The visual evidence shows the read-only preparation region with task id, SHOT_01 package and revision, candidate id, source image identifier, and shot mapping at both target viewports. The layout remains readable without overlap or horizontal overflow.

## Synchronization

The five frontend Director source/test files and this report were synchronized to the actual `main` worktree. Existing unrelated dirty changes in both worktrees were preserved. The production synchronization completed successfully.

This is an isolated offline synthetic acceptance. It does not authorize real Provider submission, paid generation, production data writes, migrations, deployment, service restart, or human Checkpoint 1/2 approval.

## Next Steps

- Keep the current `director_fixed` path read-only until the real Provider execution contract receives separate authorization and acceptance.
- Treat the formal/production frontend as `http://192.168.30.126:5173/` for any later production inspection.
