# Fashion Factory

## Current Status

This package is a **reference implementation, not a wired production feature**.
It is not imported by the API, services, runner, or provider adapters, and it does
not submit provider work. The existing task and production workflow remain the
source of truth for the execution side.

The package is retained as the execution-side reference for the OS Quality Agent
(`B-6`). In particular, `policies.py` defines the failure-code split and decision
shape that the OS layer must align with instead of creating a second taxonomy:

- `HARD_REJECT_CODES` require targeted regeneration or escalation.
- `SALVAGEABLE_CODES` may be handled by a bounded safe cut when the contract allows it.
- Unknown or high-propagation-risk errors remain non-salvageable.

## What Is Included

- Immutable product-truth, temporal-error, decision, segment, music, and pilot-run
  contracts in `contracts.py`.
- Factory state transitions in `orchestrator.py`.
- Failure classification and bounded retry decisions in `policies.py`.
- Deterministic cut alignment and render-plan lineage in `editing.py`.
- Pilot metrics in `pilot.py`.

These modules are pure contract, policy, and planning primitives. Their presence
does not mean that the corresponding provider or production workflow is enabled.

## Conditions For Future Wiring

Do not enable this package by adding an incidental import or a local feature flag.
A separate, explicitly reviewed integration task must first provide all of the
following:

1. An OS Quality Agent (`B-6`) interface and translation tests that preserve the
   failure-code taxonomy and the `Retryable` / `Human Required` / `Fatal` decision
   boundary.
2. A documented owner for each state transition and a persisted lineage contract
   for product truth, source clips, decisions, and render plans.
3. An isolated dry-run or replay validation covering provider failures, retry
   budgets, safe-cut boundaries, and human-review escalation.
4. A separately approved execution-side integration plan that does not bypass
   confirmation, idempotency, recovery, cost, or paid-submission gates.

Until those conditions are met, keep this package reference-only. Do not treat its
contracts, pilot metrics, or state machine as evidence of a completed production
pilot or a successful formal-environment acceptance.
