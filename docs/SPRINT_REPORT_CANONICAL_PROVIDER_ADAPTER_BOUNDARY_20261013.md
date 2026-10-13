# Sprint Report: Canonical Provider Adapter Boundary

日期：2026-10-13  
范围：Phase 4A - Provider Adapter Boundary  
状态：架构集成完成，未执行 Provider submission

## 完成

- 新增只读 canonical Provider adapter，将 `ImageGenerationRequest` 转换为 `ProviderRequestPreview`。
- Preview 保留 `creative_state_id`、revision、content hash、shot ID、prompt、prompt hash、preservation hash、locks hash、lock constraints、forbidden changes 和完整 Product/Character/Scene/Spatial/Camera reference manifest。
- 复用现有 `build_prediction_payload` 选择 image Provider model 和参数；prompt 原样传递，不重写、不补充创意事实。
- 在提供 execution-owned compilation context 时，生成现有 `CreativeImageProviderRequest`；task ID、source mapping、bridge token、evidence hash、text contract 和幂等键全部由 context 明确提供，不从 canonical state 猜测。
- 没有 execution context 时仍可生成 dry-run preview，但 `provider_contract_ready=false`、`provider_request=null`，且结果不可执行。
- 增加 manifest identity、preservation、Product source、Character/Scene/Spatial/Camera 和 Spatial submission gate 校验。
- `provider_submission_allowed` 与 `ProviderRequestPreview.executable` 固定为安全值；本阶段不调用 Provider、不创建任务、不写数据库、不扣费。

## 架构

```text
CreativeStateRevision
        ↓
StoryboardState
        ↓
ShotState
        ↓
ImageGenerationRequest
        ↓
Canonical Provider Adapter
        ↓
ProviderRequestPreview
        ↓
Existing CreativeImageProviderRequest (only with explicit execution context)
        ↓
Existing preflight / lease / ticket / executor
```

Canonical creative state 继续拥有 Product、Character、Scene、Spatial、Camera、Storyboard、Shot 和 continuity。Provider 层继续拥有 provider options、materialization、capability checks、submission tickets、leases、retry、remote status、UNKNOWN reconciliation 和 execution lifecycle。

## 修改

新增：

- `backend/src/libtv_agent/services/canonical_provider_adapter.py`
- `backend/tests/test_canonical_provider_adapter.py`
- `docs/SPRINT_REPORT_CANONICAL_PROVIDER_ADAPTER_BOUNDARY_20261013.md`

更新：

- `backend/src/libtv_agent/creative/image_generation_adapter.py`
- `docs/CHANGELOG.md`

没有修改：

- Kling preparation 或 Kling API；
- Provider request model 定义；
- Provider executor、submission、billing、lease 或 task execution；
- 数据库 schema；
- 前端 workflow。

## 测试

- Phase 4A adapter + Phase 3 image adapter + existing Provider request + controlled image adapter：84 passed。
- Scoped Ruff：通过。
- `compileall`：通过。
- Provider request regression 保持通过；未调用 Provider API。

覆盖重点：

- canonical request 到 Provider preview；
- 带显式 execution context 时生成现有 Provider request contract；
- preview 不凭空生成 task/source/evidence contract 字段；
- Product/Character/Scene/Spatial/Camera references 保留；
- blocked Spatial 阻止边界转换；
- 缺失 Character/Scene/Camera 保持 unresolved；
- existing Provider request 和 controlled image adapter regression。

## Phase 4A 边界验证结果

验证通过：canonical creative truth 可以安全到达现有 Provider contract boundary，同时不改变既有 Provider execution ownership。

Provider contract 的执行字段不能从 canonical state 推断。没有 context 时 adapter 只提供 preview；只有已有执行层显式提供这些字段时才构造旧 contract。所有结果仍固定为不可自动提交。

## Phase 4B 要求

1. 在单样本范围内为 Kling 建立独立 Provider-specific adapter，复用 `ShotState` 和 manifest，不复制 storyboard truth。
2. 将 Kling 所需首帧、分镜、商品素材的输入顺序映射到现有 `KlingOfficialApiAdapter` contract。
3. 继续由现有 lease、materialization、capability、submission ticket、billing、UNKNOWN reconciliation 和 executor 负责执行生命周期。
4. 为 Kling adapter 增加 dry-run、source hash、角色顺序、Spatial/continuity gate 和 provider rejection regression。
5. 在真实 Provider 调用前保留默认关闭、人工授权和单样本验证门。
