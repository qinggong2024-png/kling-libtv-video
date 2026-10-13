# Sprint Report: Canonical Creative State Foundation

日期：2026-10-13  
范围：Phase 1 - Implement CreativeState Foundation  
状态：工程实现完成，后续 Storyboard/Provider 写入仍待 Phase 2+

## 完成

- 建立 `creative-state.v1` 后端不可变领域模型。
- 建立 Product、Character、Scene、Spatial、Camera、Storyboard、Shot 和 Quality 状态对象。
- 建立 CreativeState / CreativeStateRevision 的版本、父版本、facts revision、state version 和来源边界。
- 建立内容哈希、锁项哈希、商品来源快照哈希和篡改检测。
- 建立从现有 `CreativeTask.snapshot_json`、ProductVersion、Director snapshot、CreativeRecord 和输出质量记录到 Canonical Creative State 的只读投影。
- 自动把旧任务 `snapshot.asset` 适配为 ProductState source asset，保留 SHA-256 和物化状态。
- 明确 Quality 的 `OFFLINE_SYNTHETIC_ONLY` 不得提升为 Deliverable。

## 修改

新增：

- `backend/src/libtv_agent/creative/state.py`
- `backend/src/libtv_agent/creative/state_revision.py`
- `backend/src/libtv_agent/creative/state_adapters.py`
- `backend/src/libtv_agent/creative/state_projection.py`
- `backend/tests/test_creative_state_foundation.py`

更新：

- `backend/src/libtv_agent/creative/__init__.py`
- `docs/CHANGELOG.md`

本阶段没有新增 API 路由、数据库迁移、Provider 调用、计费逻辑、配额逻辑或前端状态写入。

## 测试

- Phase 1 专项测试：7 passed。
- Phase 1 + 既有 Creative Workflow 核心回归：24 passed。
- `backend/tests/test_creative_*.py`：全量通过。
- Phase 1 文件 scoped Ruff：通过。
- Python compileall：通过。

覆盖重点：

- 旧 snake_case 快照与 Director camelCase 字段适配；
- ProductVersion 与 task snapshot 冲突诊断；
- Character/Scene/Spatial/Camera 的只读映射；
- 显式 `shot_id`、shot order 和 source binding；
- revision hash、locks hash、source snapshot hash；
- 修改已封存 revision 后拒绝；
- owner mismatch；
- AI/离线质量证据不能直接获得交付资格。

## 发现问题

- 当前 Character、Scene、Spatial、Camera 尚没有完整的服务端持久化真源；本阶段只提供只读适配，缺失时保留 `None` 或诊断。
- 旧 Creative Workflow 的部分 storyboard 仍只有 `FIRST_FRAME` / `SHOT_01`，更大镜号空间留给 Phase 2。
- 当前投影不会改变既有任务状态，也不会替换 `CreativeTask.snapshot_json` 的兼容存储。
- 未执行 PostgreSQL 带数据迁移、多 worker 崩溃恢复、真实 Provider、真实像素质量或正式版浏览器验收。

## 下一步

Phase 2 进入 Storyboard integration：

1. 让选定方向、package revision 和显式 shot ID 以 canonical revision 形式落盘；
2. 保持 FIRST_FRAME 与 VIDEO_STORYBOARD 的选择/审核独立；
3. 将 source binding 从嵌套 request JSON 迁移为可查询的 shot 映射；
4. 保留旧 automatic/custom 视频任务和历史恢复行为。

本 Sprint 不改变 Checkpoint 1/2、真实 Provider、上线或生产数据写入状态。
