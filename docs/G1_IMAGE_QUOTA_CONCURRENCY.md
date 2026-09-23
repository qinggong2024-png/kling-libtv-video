# G1 Image Quota Concurrency Increment

Date: 2026-09-23. Status: implemented and technically verified; full G1 gate remains pending.

## Scope

Serialize image batch admission with a database-backed per-user lock before both the
idempotency lookup and quota read. Hold it through batch persistence, but release it
before provider uploads/submission. A no-op update of the existing user row supports
PostgreSQL row locking and SQLite writer serialization without a schema migration.
SQLite serializes writers globally; PostgreSQL locks only the selected user.
No in-process lock is used as the correctness boundary.

Existing conservative semantics remain: persisted failed/unknown batches count for
their creation day, idempotent replay consumes no additional quota, and image and video
budgets are separate. Daily defaults are not runtime configuration evidence.

## Verification

Independent PostgreSQL 17.6 cluster on 127.0.0.1:15439, database g1_safety, unique test
schemas, plus file-backed SQLite. No existing database or production var was used.
Fake provider only; ASGI requests run in memory. An external isolated test runner
removed inherited application variables, blocked outbound connections and subprocesses,
and restricted file writes to the evidence directory. Windows internal socket pairs
and the dedicated PostgreSQL endpoint were the only permitted socket connections.

Before fix: SQLite and PostgreSQL each returned [201, 201] and made two fake generation
submissions for a daily limit of one. After fix: [201, 429], one batch and one submission.

Testing baseline and main-based candidate each passed 27 related tests, including:
- Concurrent final quota admission on both database engines.
- Concurrent identical-key replay, changed-payload conflict and user isolation.
- Lock release before provider I/O and rollback after an injected failure.
- Existing image validation, unknown submission, download recovery and quota tests.

Ruff and git diff --check passed. Existing image test helpers now install the fake
provider before application lifespan, preventing real startup credential checks.
No real provider calls, business samples, process-kill recovery, performance acceptance,
production migrations, deployment/restart or remote push were performed.

## Promotion Boundary

Testing baseline: 9ce08359f9459a21b3d8f36e3cacec059718cf49.
Main baseline: 986d57a53bb01ac3f2f5b0c17723914968a85111.
Main previously lacked image quota admission, so promotion includes only its required
service, daily_user_image_limit setting (500), API gate and relevant tests.
Main's video points defaults (5000/120) remain unchanged; testing's video-count defaults
(100/1) remain unchanged. Quality-review features and other branch-only work are excluded.
No schema migration is required. Source promotion is not runtime deployment.

## Operations and Remaining Gates

IMAGE_DAILY_LIMIT_EXCEEDED returns 429 before upload/generation. Do not retry with a new
key to evade quota. Unknown submissions retain their existing conservative treatment.
Do not remove idempotency/batch records to roll back. If an operational problem occurs,
pause new paid submissions while retaining query/download/reconciliation paths.

Full G1 still requires the remaining approved fault matrix, including real process
restart, callback/poll races, cancellation races, comprehensive Shanghai-day recovery,
observability/redaction and storage faults. This increment does not authorize G2.
Implementation and technical verification: assistant in this task. Business acceptance
and runtime release approval: pending user-designated owner.
