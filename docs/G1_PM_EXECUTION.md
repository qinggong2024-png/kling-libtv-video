# G1 PM Execution Board

Baseline 2026-09-24: testing 0f0c394, main f7574a3. Latest external UI/recovery
API additions are preserved. G1 and UI release matrices use separate ID namespaces.

## Ownership And Acceptance

The parent agent owns scope, integration, evidence review, branch promotion and
release conclusions. Child agents provide bounded implementation or review work;
their summaries alone never count as acceptance evidence. Prefer mini/high for
bounded audits, escalate only when the actual problem requires it.

Delegation incident: multiple children reported empty task bodies. Stop assigning
implementation work through that channel until delivery is confirmed. Parent
continues local execution. No child changed source in this cycle.

## Work Packages

| Package | State | Required evidence |
| --- | --- | --- |
| G1-S03 socket disconnect | Verified scoped case | Production HTTP transport accepts one POST, drops response; SQLite/PostgreSQL persist unknown; replay and default-adapter replacement do not post again |
| G1-S04 recovery | Open | Main lacks testing recovery implementation; review minimal port, protect stale observation races, then actual launch crash tests |
| G1-S05 callback | Decision required | Existing anonymous callback lacks source authentication; callback/poll stale writes and current-provider routing need fixes |
| G1-S06 retries | Open | HTTP-date Retry-After and bounded retry matrix per supported provider |
| G1-S07/S08/S10 | Open | Delivery faults, cancellation/success race, Shanghai cross-day ledger |
| G1-S11/S12 | Partial | Reconnection/REST truth and response/audit/metric confidentiality; logging patch alone is insufficient |
| UI privacy | Verified source risk | IndexedDB active draft is shared across accounts; scope draft ownership and test logout/account switch |
| UI unknown submission | Verified source risk | Regenerate action available for unknown results; persist submission identity and enforce reconciliation |

## Major Decision

No supplier callback authentication contract is established. The recommended
interim release policy is to reject callbacks by default and retain provider-bound
polling for existing work, with no resubmission or release of unknown charges.
Changing an externally integrated endpoint is a compatibility decision requiring
user approval before implementation. An alternative is a documented authenticated
gateway supplied by the deployment owner; do not invent a vendor HMAC header.

Approval would authorize source changes and isolated verification, not live service
restart, production data changes or paid API calls. Polling coverage must be proven
before any deployment of callback disablement.

## Evidence

External G1 evidence root ends in 01a0cdb7-c7c6-7840-ab2f-0c932e004dc2/G1.
socket-fault-integration.xml: 3 passed on isolated testing baseline. This does not
prove actual process termination during POST or full G1 completion. The initial
fixture failed the configured-unverified guard before any POST; the corrected
fixture explicitly sets synthetic verification while preserving actual transport.

Only scoped source, tests and this board are promoted. No secrets, runtime files,
database state, service restart, migration, remote push or paid call is authorized.
