# Sprint Report：Director Studio V2 Sprint 6

日期：2026-10-14
范围：恢复 Director Workflow MVP 的真实任务调用；不开放 Provider 生成。

## 完成

- 新增显式 `DIRECTOR_WORKFLOW_MODE` 配置，支持 `offline_demo` 与 `live_director`。
- `offline_demo` 保留原有 `OFFLINE_WORKFLOW_DISABLED`、付费模式和本地对象存储边界。
- `live_director` 放行已有 Director 任务创建、任务读取、`analyze` 和 `select_direction` 调用。
- Live 响应标记为 `LIVE_DIRECTOR`，前端显示“Live Director · 仅导演分析”。
- Live Director 下隐藏 Offline Fake 首帧授权和生成入口。
- 未修改 Agent、Provider、图片/视频生成、Prompt、`select_direction` 实现、Production Package 内容或 package contract。

## 修改

- `backend/src/libtv_agent/config.py`
  - 增加 `director_workflow_mode`，默认 `offline_demo`。
- `backend/src/libtv_agent/api/creative_workflow.py`
  - 将无条件离线门改为显式 Director 运行模式门。
  - 创建、读取和命令响应返回当前 Director 运行模式。
- `backend/src/libtv_agent/api/system.py`
  - 在系统状态和配置指纹中报告 Director 运行模式。
- `frontend/src/features/director-studio/DirectorStudio.tsx`
  - 根据服务端模式显示运行状态；Live 模式不展示 Fake 生成操作。
- `frontend/src/features/director-studio/directorApi.ts`
  - 补充 `LIVE_DIRECTOR` 响应类型。
- `.env*.example`
  - 增加 `DIRECTOR_WORKFLOW_MODE=offline_demo` 示例。
- `backend/tests/test_config.py`
  - 增加默认值和 Live 模式配置测试。
- `backend/tests/test_creative_workflow.py`
  - 增加 Offline 保持阻断和 Live `analyze → direction` 测试。
- `docs/CHANGELOG.md`
  - 记录 Sprint 6 范围和边界。

## 数据流

Live 模式复用现有链路：

```text
商品图片 + 已接入品牌上下文
→ POST /creative-workflow/tasks
→ POST /creative-workflow/tasks/{id}/commands { action: "analyze" }
→ 现有 Director Analysis
→ 现有 A/B/C Direction Candidates
→ 现有 select_direction
→ 现有 Production Package
```

高级创作设置仍按 Sprint 4 约定标记为计划支持，不被伪装成已接入分析参数。

## 测试

- 后端：`backend/tests/test_creative_workflow.py`、`backend/tests/test_config.py` 通过。
- 后端 Ruff：通过。
- 前端 Director 相关单测：3 个文件、21 项通过。
- 前端全量单测：58 个文件、408 项通过。
- 前端 build：通过。
- 前端 lint：通过。
- `git diff --check`：通过。

## 运行状态边界

- `offline_demo`
  - 仅支持离线 Fake 流程验证。
  - 在非 test 环境、非 fake/replay 适配器、付费模式或非本地对象存储条件下继续拒绝。
- `live_director`
  - 仅开放 Director 分析和方向选择链路。
  - 不代表 Provider 已配置，不代表图片或视频已生成，不代表素材可交付。
  - 付费生成仍由既有独立门禁阻断。

## 未接入能力

- 未接入新的 Agent 或外部模型调用。
- 未接入图片生成、视频生成、Provider 提交、计费或生产交付。
- Sprint 4 标记为“计划支持”的高级 Brief 字段仍未进入后端分析。
- 当前 Director Analysis 仍复用既有服务端分析实现，方向候选不会因为本 Sprint 自动获得新的生成能力。

## 下一步

- 在隔离环境将 `DIRECTOR_WORKFLOW_MODE=live_director` 接入人工样本验证。
- 验证 5 个真实商品样本的方向差异、选择理由和 Production Package 完整性。
- 根据失败样本决定是否需要后续产品或分析能力调整。
