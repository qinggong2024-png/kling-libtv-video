# Creative Memory Boundary

状态：前端 schema/interface/adapter 预备层
日期：2026-10-12
范围：Creative Project 上下文内的创意历史记录，不是任务历史或生产状态存储。

## Purpose

Creative Memory records decisions that help a CreativeProject explain how it evolved:

- `direction-history`: direction 的创建、修改、归档和恢复；
- `candidate-selection`: candidate 的 shortlist、select、reject 和 clear；
- `production-package-revision`: production package revision lineage；
- `bridge-decision`: Production Bridge 的准备、阻断、拒绝和 handoff decision。

Every entry is scoped by `projectId`, append-only, and carries both the creative event time
(`occurredAt`) and local record time (`recordedAt`). The adapter returns a chronological copy,
so callers cannot mutate stored records through a returned object.

## Ownership

Creative Memory is owned by `CreativeProject`. It is separate from:

- existing Task history, task phase, execution state, polling and recovery;
- Provider state, provider task IDs, billing, quota and ledger;
- image/video generation outputs and delivery qualification;
- the Creative Workflow API contract.

The schema rejects task/provider/billing state keys such as `phase`, `status`,
`stateVersion`, `providerTaskId`, `billingStatus`, `quota` and `ledger`. This is a
boundary check, not a replacement for server-side validation.

## Production Bridge

Bridge decisions may reference a package ID, package revision, shot purpose and blocking
reason codes. They deliberately preserve `providerSubmissionAllowed: false`. Recording a
bridge decision does not submit work, change task state, authorize a Provider, or mark an
asset as production-qualified.

## Adapter Contract

`InMemoryCreativeMemoryAdapter` is a preparation adapter for frontend tests and local
composition. It is not a persistence core model and does not introduce an API route,
database table, migration, synchronization worker or server ownership.

Any future durable adapter must preserve:

1. project scoping and append-only semantics;
2. the four discriminated event kinds;
3. separation from Task history and execution state;
4. the read-only Production Bridge boundary;
5. server/API approval before network persistence is introduced.
