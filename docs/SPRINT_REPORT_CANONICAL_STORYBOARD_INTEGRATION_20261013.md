# Sprint Report: Canonical Storyboard Integration

日期：2026-10-13  
范围：Phase 2 - Storyboard Integration  
状态：工程实现完成，Provider/Image/Kling adapter 仍待后续阶段

## 完成

- 将 Director campaign intent、hook、情绪推进、商品证据、CTA 和 selected direction 编译到 `StoryboardState`。
- 将 legacy storyboard package 编译为显式有序 `ShotState[]`，保留 shot ID、order、duration、entry/exit state、action、camera language 和 source binding。
- 为每个 shot 写入 Product、Character、Scene、Spatial、Camera 的 canonical revision 引用；缺失引用进入 `unresolved_references`。
- 增加 shot intent/purpose 和动作能力校验状态，保留 `required`、`confirmed`、`denied` 与 `VALIDATED` / `UNRESOLVED` / `BLOCKED` 结果。
- 增加 canonical storyboard validation。缺失或未验证 Spatial 会阻止 executable 状态；Character、Scene、Camera 缺失会明确报告 unresolved，不填充虚构事实。
- 保留现有 `CreativeTask.snapshot_json`、`FIRST_FRAME` / `VIDEO_STORYBOARD` 兼容路径；没有改 Provider 执行链。

## 修改

新增：

- `backend/tests/test_creative_storyboard_integration.py`
- `docs/SPRINT_REPORT_CANONICAL_STORYBOARD_INTEGRATION_20261013.md`

更新：

- `backend/src/libtv_agent/creative/state.py`
- `backend/src/libtv_agent/creative/state_adapters.py`
- `backend/src/libtv_agent/creative/state_projection.py`
- `backend/src/libtv_agent/creative/__init__.py`
- `docs/CANONICAL_CREATIVE_STATE_ARCHITECTURE_20261012.md`
- `docs/CHANGELOG.md`

本阶段没有新增 API 路由、数据库迁移、Provider request contract、Kling preparation、质量自动审核、前端页面或新的 agent。

## 测试

- Phase 2 专项 + Phase 1 foundation + legacy storyboard：14 passed。
- `backend/tests/test_creative_*.py` Creative 全量回归：通过。
- Phase 2 scoped Ruff：通过。

覆盖重点：

- Director package 到 StoryboardState 的 campaign projection；
- 多 shot 显式 ID、顺序、时长、镜头语言和 inherited state references；
- continuity rules 在 `CreativeStateRevision` 封存后保持不变；
- 缺失 Spatial 不被编造成默认值，并使 canonical state 不可 executable；
- legacy Creative Workflow storyboard regression。

## 架构偏差与限制

- 为了无损保留 legacy package 的 camera language 和 action capability check，本阶段在 ShotState 增加了结构化 adapter metadata；这些字段仍属于 creative identity，不包含 Provider lifecycle。
- Character、Scene、Spatial、Camera 仍没有完整服务端持久化真源；本阶段仅通过现有 intelligence snapshot 生成只读引用。
- 当前 legacy Creative Workflow 的 storyboard 仍主要提供 `FIRST_FRAME` / `SHOT_01`；adapter 支持显式多 shot order，但不会凭空扩展缺失镜头。
- validation 已建立 executable/blocking 结果，但尚未接入 Provider submission；Provider 接入留给后续阶段。

## 下一步

1. 让 Image generation adapter 从 validated `CreativeStateRevision` 和 `ShotState` 读取 canonical source binding。
2. 保持 Provider request contracts 不变，并在 adapter 层加入 canonical preflight。
3. 后续再接 Kling adapter 和 Reality validation，继续保持 Spatial 与 continuity gate。
