# Controlled Image Bridge Preflight v1

Date: 2026-10-12
Scope: CRB-1, FIRST_FRAME image preparation only.

## Endpoint

`POST /api/v1/creative-production-bridge/tasks/{task_id}/preflight`

Authenticated owner access and the existing review-write/CSRF controls apply.
Administrators still require task ownership. Auditor access is denied.
This additive endpoint does not change the Creative Workflow API or its
offline-only and live-execution gates.

Request:

```json
{"expected_version": 3}
```

`task_id` is a UUID. `expected_version` is a strict, nonnegative integer.
Unknown fields, strings, booleans and fractional versions are rejected.
Provider/model overrides, approval paths, execution modes and permission
booleans are not accepted from clients.

## Server Authority

The application does not enable this endpoint automatically. Missing policy
or `ControlledImageBridgePolicy(enabled=False)` fails closed.

A trusted server integration may supply
`app.state.controlled_image_bridge_policy`, with bindings keyed by task UUID.
Each `ControlledImageBridgeBinding` contains existing `ImageProviderOptions`,
`ProviderCapabilityDeclaration` and a server-local approval manifest path.
The policy copies and freezes its binding mapping.

Enabling policy requires separately integrated CreativeTask, request compiler
and production preflight dependencies. Those preparation packages are not
included in CRB-1. Missing dependencies return 503; default-disabled service
imports do not require those packages.

## Validation And Evidence

The service checks owner and task version, compiles the immutable production
package with the existing compiler, and invokes the existing production
preflight validator for source/hash, approval, license, quote, quota and
paid-generation/pause controls. It closes the temporary input lease before
returning.

Success fields include task/version, package revision, FIRST_FRAME, provider,
model, request/evidence/preflight hashes, reference count and expiry.
Prompt contents, local paths and object-store keys are excluded.

The following response values are fixed:

```json
{
  "schema_version": "controlled-image-bridge-preflight.v1",
  "status": "READY_FOR_HUMAN_SUBMIT",
  "execution_mode": "PREFLIGHT_ONLY",
  "actual_submitted": false,
  "provider_submission_allowed": false,
  "provider_capabilities_verified": false,
  "qualification_scope": "OFFLINE_SYNTHETIC_ONLY",
  "deliverable_eligible": false
}
```

`READY_FOR_HUMAN_SUBMIT` describes preflight evidence only. It grants no
execution permission and does not establish verified Provider capability,
real output quality or delivery eligibility.

## Errors

Service rejection format: `{"detail":{"code":"..."}}`.
Existing authentication, role and CSRF controls retain their error formats.

| HTTP | Code / Condition |
| --- | --- |
| 403 | CONTROLLED_BRIDGE_DISABLED |
| 403 | CONTROLLED_BRIDGE_BINDING_REQUIRED |
| 404 | CREATIVE_TASK_NOT_FOUND, including another owner's task |
| 409 | STALE_VERSION or existing compiler/preflight rejection code |
| 422 | Invalid UUID or invalid request shape/type |
| 503 | CONTROLLED_BRIDGE_DEPENDENCIES_UNAVAILABLE |

## Effects And Limits

No Provider upload or submission, ticket admission, task transition,
reservation, settlement, quota/ledger mutation or deliverable creation.
Temporary materialization is local to the validator lease.

CRB-2 ticket binding and CRB-3 production submission remain separate work.
No environment activation, migration, deployment or service restart is part
of this contract. A future real call requires request-specific authorization,
Provider/model, immutable source/package, call limit, budget/currency and
expiry. Frontend readiness and a successful preflight cannot replace them.
