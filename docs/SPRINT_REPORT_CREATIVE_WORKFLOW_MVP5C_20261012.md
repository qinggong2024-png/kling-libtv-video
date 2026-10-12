# Sprint Report：Director Studio Workflow MVP

日期：2026-10-12
范围：基于 Creative Workflow API Contract v1 补齐 Director Studio 的首帧到 SHOT_01 分镜交互闭环。

## 完成

- 保留现有 Product Intake、Direction Candidates、Production Package 和首帧闭环。
- 新增首帧选择后的 `VIDEO_STORYBOARD` 授权门槛。
- 新增 `SHOT_01` storyboard package、Fake generation、review 和 selection 的独立 UI 状态。
- 保留 `state_version`、`command_key`、服务端 snapshot、错误恢复和 offline qualification 边界。
- 保留 `OFFLINE_SYNTHETIC_ONLY` 与“选择不等于交付资格”的展示。
- 分镜授权沿用服务端要求的 `parent_authorization_id`，未新增 API endpoint 或 Provider 调用。

## 修改

- `frontend/src/features/director-studio/DirectorStudio.tsx`
- `frontend/src/features/director-studio/directorApi.ts`
- `frontend/src/features/director-studio/directorModel.ts`
- `frontend/src/features/director-studio/directorSelectors.ts`
- `frontend/src/features/director-studio/directorAdapters.ts`
- `frontend/src/features/director-studio/contracts.ts`
- `frontend/src/features/director-studio/directorStudio.css`
- Director Studio API、model 和 browser fixture tests

## 测试

- `frontend`: build 通过。
- `frontend`: lint 通过。
- `frontend`: Vitest 40 个测试文件 / 267 项通过。
- Director Studio browser check：1440px 和 390px 均通过，各 18 条命令；覆盖首帧拒绝、刷新恢复、重新选择、分镜授权链、分镜生成、审核、拒绝恢复和选择。
- Video Studio regression：13 个既有场景通过。
- main 工作树：build、lint、Vitest 41 个测试文件 / 263 项通过；Director Studio browser check 两个视口通过。
- 已查看 1440px 与 390px workflow evidence，页面无横向溢出，首帧和 SHOT_01 状态分区清晰。

## 发现问题

- `VIDEO_STORYBOARD` 授权必须在首帧人工审核合格并选择后才能开放。
- storyboard 候选、审核和选择不能复用首帧的旧字段；前端通过 `storyboard.packages`、`storyboard.candidates`、`storyboard.selections` 和 `storyboard.latest_reviews` 分离读取。
- 当前 Fake 输出仍为 `OFFLINE_SYNTHETIC_ONLY`，不可交付，也没有接入真实视频生成或 Provider。
- 未修改 `frontend/src/api.ts`、后端、路由和既有生产流水线。

## 下一步

- 等待人工确认是否进入下一阶段。
- 任何真实 Provider、Video Studio 生产桥接、付费调用或交付语义变化都需要单独批准。
