# Sprint Report: Canonical Image Generation Adapter

日期：2026-10-13  
范围：Phase 3 - Image Generation Adapter  
状态：工程实现完成，Provider/Kling 执行接入仍待后续阶段

## 完成

- 新增 `CreativeStateRevision` + `ShotState` 到 provider-neutral `ImageGenerationRequest` 的编译适配器。
- 将 Product、Character、Scene、Spatial、Camera 和 Shot 的 canonical 内容保留在请求边界中。
- 为每个请求生成 `ImageReferenceManifest`，包含 `creative_state_id`、revision、shot ID、来源引用和 preservation hash。
- 将 Product locks、商品 preservation constraints、Character continuity、Scene constraints、Spatial relationships、Camera intent、Shot purpose/action/evidence 和 continuity rules 编译到 image request。
- 在编译前验证 revision hash integrity、selected shot 身份、Product source asset、action capability、prompt revision、preservation hash 与五类 inherited state revision。
- 缺失 Character、Scene 或 Camera 返回明确 `UNRESOLVED`；缺失或未验证 Spatial、缺失 Product source 或未验证 action capability 返回 `BLOCKED`；不生成虚构 creative facts。
- `provider_submission_allowed` 固定为 `False`；适配器不调用 Provider、不写数据库、不创建任务、不扣费、不改变现有图片执行链。

## 修改

新增：

- `backend/src/libtv_agent/creative/image_generation_adapter.py`
- `backend/tests/test_creative_image_generation_adapter.py`
- `docs/SPRINT_REPORT_CANONICAL_IMAGE_GENERATION_ADAPTER_20261013.md`

更新：

- `backend/src/libtv_agent/creative/__init__.py`
- `docs/CHANGELOG.md`

本阶段没有修改 Provider API、Provider execution、Kling logic、数据库 schema、前端页面或 Quality 自动审核。

## 适配器架构

```text
CreativeStateRevision
        +
Selected ShotState
        |
        v
Canonical ImageGenerationAdapter
        |
        v
ImageGenerationRequest
        |
        v
Future Provider-specific adapter
```

现有仓库的 `CreativeImageProviderRequest` 仍绑定旧 CreativeTask、数据库记录、候选媒体和 Provider preflight，不能直接由 canonical revision 构造。因此本阶段使用 provider-neutral `ImageGenerationRequest` 作为边界合同，保留既有 Provider request contract 不变。后续转换必须再次执行 Provider-specific reference materialization 和 preflight。

## 测试

- Phase 3 adapter + Phase 1 foundation + Phase 2 canonical tests：42 passed。
- Existing image workflow regression：106 passed。
- Scoped Ruff：通过。
- `compileall`：通过。
- `git diff --check`：通过。

覆盖重点：

- 完整 revision 和 selected shot 成功编译；
- 多 shot 保留 shot ID、顺序和 Product/Character/Scene/Spatial/Camera 引用；
- manifest 保留 creative state identity、revision、source references 和 preservation hash；
- blocked Spatial 阻止 image request；
- 缺失 Character/Scene 返回 unresolved；
- revision 外 shot 被拒绝；
- 旧 image bridge、Provider request 和 workflow orchestrator regression。

## 架构偏差与限制

- 本阶段新增的是 provider-neutral image request，而不是替换旧 `CreativeImageProviderRequest`；这是为了避免把 canonical state 与旧 CreativeTask/数据库/provider preflight contract 强耦合。
- 当前 adapter 只验证 canonical references 和 source object identity，不负责下载、字节复核、临时物化、Provider capability、费用或人工授权。
- `provider_submission_allowed` 仍固定为 `False`，所以 `READY` 只表示 canonical image request 可交给后续 Provider adapter，不表示已经可以提交或生成。
- Character、Scene、Spatial、Camera 的真源仍来自现有 read-only projection/intelligence snapshot；本阶段没有新增持久化或数据库迁移。

## Phase 4 要求

1. 为 `ImageGenerationRequest` 增加显式 Provider-specific conversion adapter，并保持现有 Provider request contract。
2. 在 Provider adapter 中重新验证 source object 是否存在、字节 hash、许可、角色顺序和输入物化 lease。
3. 继续保留默认关闭、人工授权、费用额度、幂等、UNKNOWN 对账和停止状态边界。
4. 在单样本范围内接入真实 image Provider 前置验证；不要在 conversion adapter 中直接绕过现有 submission/preflight。
5. 后续再评估 Kling/video adapter 如何复用 ShotState、continuity 和 manifest，而不复制第二套 storyboard truth。
