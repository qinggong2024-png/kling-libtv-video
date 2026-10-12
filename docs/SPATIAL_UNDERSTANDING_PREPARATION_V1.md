# Spatial Understanding Preparation v1

## Scope

Window 4 prepares contract-only representations for future spatial understanding:

- Spatial DNA
- relative depth references
- static camera-to-subject relationships
- motion reference placeholders

These artifacts are planning inputs and review metadata. They do not perform
depth estimation, video analysis, video replication, provider submission, or
production execution.

## Hard Boundary

Every generated object is constrained to:

- `mode: OFFLINE_SYNTHETIC_ONLY`
- `preflightStatus: PREFLIGHT_REQUIRED`
- `providerSubmissionAllowed: false`

The Production Bridge remains the only future entry point for production
handoff. This window does not add a route, API client, task state, ownership
mutation, billing/quota/ledger behavior, or provider adapter.

## Contracts

| Contract | Machine-readable schema | Intended use |
| --- | --- | --- |
| Spatial DNA | `backend/contracts/spatial-dna.schema.json` | Aggregate spatial observations |
| Depth reference | `backend/contracts/depth-reference-contract.schema.json` | Relative depth bands and ordering |
| Camera relationship | `backend/contracts/camera-relationship.schema.json` | Static relationship and framing language |
| Motion placeholder | `backend/contracts/motion-reference-placeholder.schema.json` | Non-executable motion intent |

The frontend interface and pure offline adapter live under
`frontend/src/features/spatial-understanding/`. They are intentionally not
mounted into `CreativeProject` and do not change project ownership.

## Promotion Rule

Any later integration must first obtain a server-validated package, materialized
source mapping, authorization evidence, and Production Bridge preflight. These
schemas alone never authorize execution.
