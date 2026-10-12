# Task Completion Report: Window 3 Reality Engine Integration Preparation

日期：2026-10-12
范围：Reality Engine Integration Preparation（P1）
分支：`codex/window3-reality-engine-integration-prep`，测试基线：`codex/testing`

## 完成内容

本窗口只建立 schema、interface、adapter 和文档边界，连接关系为：

```text
CreativeProject
  └── CreativeIntelligenceSnapshot
        ├── Character DNA
        ├── Scene DNA
        ├── Camera DNA
        ├── Style DNA
        └── Reality Snapshot
              └── Production Bridge mapping
```

新增 `frontend/src/creative-project/reality.ts`：

- `CharacterDNA`
- `SceneDNA`
- `CameraDNA`
- `StyleDNA`
- `RealitySnapshot`
- `RealitySnapshotMapping`
- `RealityEvidence`
- `OFFLINE_SYNTHETIC_ONLY` execution mode
- `PREFLIGHT_REQUIRED` snapshot status

新增 `frontend/src/creative-project/realityAdapters.ts`：

- `mapRealitySnapshotToCreativeIntelligence`
- `mapCreativeIntelligenceSnapshotToReality`
- `attachRealitySnapshotToProject`
- `selectRealitySnapshot`

`CreativeIntelligenceSnapshot` 只增加可选扩展字段，保留原有
`realityReference`、`spatialReference`、`videoReference` 和 `referenceStrength`。
现有 `CreativeProject` revision 仍然是项目元数据 revision，不承载 Task phase 或执行状态。

现有 `Production Bridge` 现在输出只读 `reality` mapping，并固定：

- `status = PREFLIGHT_REQUIRED`
- `executionMode = OFFLINE_SYNTHETIC_ONLY`
- `providerSubmissionAllowed = false`

## Ownership 约束

- `CreativeProject` 持有项目级 intelligence snapshot 引用。
- `CreativeIntelligenceSnapshot` 持有 DNA 与 Reality Snapshot 的可选扩展。
- Production Bridge 只读取 handoff 和 snapshot，输出 preflight preparation。
- Task state、Provider、图片生成、视频生成、API、billing、quota、ledger 仍由原模块持有。
- Reality DNA id 和 snapshot id 是不透明标识，不在前端推导业务含义。

## 明确未做

- 未接入真实 Reality Engine 或任何真实模型。
- 未修改图片生成流程、`frontend/src/api.ts`、后端 API 或 API Contract。
- 未修改 Task state、Provider、billing/quota/ledger。
- 未创建真实生产任务、Provider submission、真实素材 materialization 或交付资格。
- 未把 synthetic reference 解释为真实 qualification 或 deliverable。

## 验收

新增测试覆盖：

- Reality Snapshot 映射到现有 `CreativeIntelligenceSnapshot` 扩展边界。
- Reality Snapshot 附加到 `CreativeProject` 时只改变 metadata revision 和 intelligence snapshot。
- Production Bridge 只读 mapping 的稳定 DNA ids。
- `OFFLINE_SYNTHETIC_ONLY` / `PREFLIGHT_REQUIRED` runtime shape guard。

测试分支验证：

- `npm.cmd run test -- --run`：PASS，42 个文件 / 274 个测试。
- `npm.cmd run lint`：PASS。
- `npm.cmd run build`：PASS。

生产同步按仓库 `AGENTS.md` 执行：先在测试分支验证，再将同一源码与文档变更同步到 `main`，不同步 secrets、runtime state 或 generated artifacts。
