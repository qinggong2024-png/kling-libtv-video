# Offline Pages Acceptance: 2026-10-08

## Scope And Evidence

Baseline: testing `e12bbf6`, main `092bb69`. This increment extends the previous
image-only checks. It is not full U08 acceptance or live production validation.
The real App, shell, lazy pages, navigation, API client and CSS are mounted via
an isolated Vite server with `configFile: false` and `envFile: false`.

Evidence root:
`C:/Users/Reel/Documents/libtv-ui-review-evidence-20261008/pages-followup`.
Final reports/screenshots are under `testing-final-2` and `main-final-2`.
Use each `result.json` for its actual pass status, case list, base HEAD, source
hashes, browser version and capture time. Testing used Edge 154.0.4258.62.
Source hashes identify uncommitted tested increments as well as committed files.

The complete invocation defines 66 cases:

| Cases | Pages / states | Widths |
| --- | --- | --- |
| 32 | Video composer, records, library actions, settings, admin overview/accounts/providers/security, populated synthetic fixtures | 1440, 1024, 768, 390 |
| 16 | Composer, records, library actions and accounts, empty fixtures | All four |
| 7 | Feature GET failures on all above pages except records | 390 only |
| 7 | Held feature GETs with visible loading indicators, except records | 390 only |
| 4 | USER direct links to all admin sections, visible denial and smoke rejection | 390 only |

Assertions cover specific visible pages/headings, active admin section/role,
page errors, document horizontal overflow, loaded synthetic images, applicable
empty/error/loading indicators, and task-row title/error geometry.
Selected workflows also check local composer image upload/Enter preview/Escape
focus return, records search/no-match/clear and URL query, and library arrow/Home
scope tabs with focus plus search/no-match/clear.
No generate, approve, save, deactivate, password or provider verification command
is clicked. Provider capability and settings switches are not acceptance targets.

## Verified Defects And Changes

- Route smoke previously accepted hidden mounted pages because it checked generic
  selector existence. It now checks visible scoped content and the exact page
  heading. Each admin subpage also requires its matching section and ADMIN role;
  login and visible permission-denial states cannot pass.
- A real 390px records layout defect was reproduced separately at
  `testing-row-before-fix`: a long error code squeezed title width to 12px even
  though document width was exactly 390px. Thus page-level overflow alone was
  insufficient. The scoped CSS change wraps long reasons and gives narrow-screen
  status its own grid row with the arrow retained beside the title.
- `testing-final` passed all 66 cases after that fix; the 390px title width was
  236px and the reason wrapped within 332px. Screenshot inspection confirmed it.
  Production promotion must keep its other CSS differences intact.
- Two bounded agents supplied smoke changes/tests and synthetic admin GET data.
  Parent reviewed both and corrected a navigation-label typo via actual-browser
  checks. Four fixture-contract tests plus ten smoke regression tests pass.

Earlier `testing` and `testing-verified` directories are retained diagnostics,
not final acceptance. Initial failures included invalid synthetic parent phases,
hidden-page error lookup and a label mismatch. The pre-layout-fix run lacked the
new internal geometry gate; its pass does not override the final regression.
The first `main-final` run had one premature Home-key focus assertion. The
component restores tab focus on the next animation frame; the harness now waits
for the same required selected/focused DOM state instead of sampling immediately.
The failure is retained, not recategorized as a pass.

## Safety And Reproduction

Use already-installed Node/Vite/Playwright/Edge; no npx or downloads:

```powershell
$env:PLAYWRIGHT_MODULE = '<installed-playwright-entry>'
$env:UI_PAGES_REPORT_DIR = '<external-evidence-directory>'
Remove-Item Env:UI_PAGES_ROUTE -ErrorAction SilentlyContinue
node scripts/ui-pages-offline-check.mjs
node --test scripts/ui-smoke.test.mjs scripts/ui-page-responses.test.mjs
```

`UI_PAGES_ROUTE=records` supports a scoped diagnostic run; inspect selectedRoutes
and never treat that run as the complete matrix. HTTP requests outside the local
fixture are aborted. Every API write is rejected; unmatched GETs fail acceptance.
All JSON/media are synthetic; providers are disabled and credentials absent.
Vite cache and reports stay outside the checkout; browser/server close on exit.
There is no live login, backend server, Runner/Pilot, production restart, real
environment/database/runtime edit, paid call or build output in this increment.

## Remaining Gates

U08 stays partial: this is small-fixture correctness/responsiveness, not performance.
Not accepted: 50/200/1000 records, first paint/filter/scroll/memory, repeated media
resource release, all keyboard workflows, contrast/high-contrast, 200% browser
zoom, enlarged fonts, mobile soft keyboard or all error states at all widths.
Reduced-motion emulation was used for stable captures, not a motion-policy audit.
Whole-app fixed-toolbar safe areas and scroll reachability remain open; full-page
screenshots alone cannot establish them. Library styles/subjects, task details,
real server authorization/session expiry and paid flows are outside this batch.
Image cross-device recovery, quota display and overlay/linked zoom remain open.
Source promotion and main-checkout fixtures do not certify the production URL.
