# Project Workflow

## Test And Production Synchronization

- Treat `codex/testing` as the test branch and `main` as the production branch.
- For every requested change to this project, implement and validate it on the test branch, then synchronize the same change to the production branch before completing the task.
- Skip production synchronization only when the user explicitly says to delay or omit it.
- Preserve production-only behavior when promoting changes; compare the branches and resolve differences instead of overwriting the production tree blindly.
- Never synchronize local secrets, runtime state, generated artifacts, caches, or the real `.env` file. Source files, safe configuration examples, tests, and relevant documentation should be synchronized.
- At the end of each change, verify both worktrees and report whether the production synchronization succeeded.

## AI Creative Studio Delivery V1.0

- The formal/production frontend is `http://192.168.30.126:5173/`; older documents naming another port do not override this user-defined entry point.
- Before every development change, read `docs/PRODUCT_SPEC.md`, `docs/DESIGN_SYSTEM.md`, `docs/DEVELOPMENT_PLAN.md`, `docs/QA_CHECKLIST.md`, and `docs/CHANGELOG.md`. Read `docs/TECHNICAL_AUDIT_20261008.md` for the intake baseline.
- Own task breakdown, architecture, frontend implementation, QA, defect repair, and scoped promotion. Product direction, business priority, usability acceptance, and launch approval remain human decisions.
- Freeze the product workspaces to `/studio/image`, `/studio/video`, `/tasks`, and `/library`. Preserve existing operational admin/settings functions without expanding them into new product modules.
- Keep the existing React/TypeScript/Vite stack unless a separately justified migration is approved. Reuse shared components, API clients, and domain presentation helpers.
- Develop Design System and Video Studio first. Stop at Checkpoint 1 for human direction acceptance before expanding Image Studio, Task Center, and Library. Stop at Checkpoint 2 for human launch acceptance.
- The new V1.0 documents govern frontend scope, page structure, and design. They do not waive existing L1-L4 quality gates, authentication, idempotency, billing, recovery, or delivery contracts.
- Run build, lint, and relevant tests for frontend changes. Run isolated browser workflows and visual checks for interaction changes; documentation-only changes do not count as renewed browser acceptance.
- Record each Sprint using `docs/SPRINT_REPORT_20261008.md` as the report format: completion, changes, tests, findings, and next steps. Fix discovered in-scope defects, rerun tests, and record limitations honestly.
- Source promotion is not live deployment or permission for paid generation, production data writes, migrations, or service restarts.
