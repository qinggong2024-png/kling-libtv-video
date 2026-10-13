# Sprint Report：Director Studio V2 Sprint 3

日期：2026-10-13
本轮范围：Creative Direction 前端展示层；将方向选择卡升级为创意决策卡

## 完成

- 将 `Direction Card` 扩展为标题、Creative Summary、Execution Concept、Visual Proposal、Information Source 和选择状态。
- 将已有 `scene`、`behavior` 标为 `AI Result`。
- 将已有 `camera`、`emotion` 标为 `Creative Proposal`。
- 保留 `User Input` 与 `Unknown` 的来源说明，不生成缺少的目标受众、商品证据和取舍风险。
- 移除独立的“方向差异对比”区域，避免 scene / behavior 重复展示。
- 保留点击选择、确认调用 `select_direction`、确认后锁定和 Production Package 原有流程。
- 桌面端保持三张等宽方向卡，移动端改为纵向排列。

## 修改

- `frontend/src/features/director-studio/DirectorStudio.tsx`
- `frontend/src/features/director-studio/DirectorPlanningViews.tsx`
- `frontend/src/features/director-studio/directorPresentation.ts`
- `frontend/src/features/director-studio/directorStudio.css`
- `frontend/src/features/director-studio/directorPresentation.test.tsx`
- `frontend/src/features/director-studio/DirectorStudio.browser-check.mjs`
- 本报告

未修改后端 workflow、`select_direction`、Agent、方向生成逻辑、Provider 或 Production Package 数据结构。

## 测试

- `frontend`: `npm run build` 通过。
- `frontend`: `npm run lint` 通过。
- `frontend`: `npm run test` 通过，56 个测试文件 / 396 项测试。
- 隔离 Director Playwright fixture 通过：1440、1024、768、390 四个视口均通过。
- 浏览器流程验证点击方向不创建 Production Package，确认方向后只发送一次 `select_direction`，后续 Fake review、刷新、选择和 storyboard 流程通过。
- 390px 验证方向卡纵向排列、页面无横向溢出，方向名和选择动作在首屏可见。
- 浏览器 fixture 阻断外部请求；首次默认 Edge 不存在，改用本机 Chrome 显式路径完成验证。

## 发现问题

- 当前服务端方向接口仍只提供 `id`、`scene`、`behavior`；summary 在现有前端映射中由这两个字段组成。
- `camera`、`emotion`、`human` 仍来自已有前端规划参考，已明确标记为创意提案，不能视为 AI 分析证据。
- 当前没有真实的 Target Audience、Product Evidence 或 Trade-off 数据，界面只显示 Unknown 说明。
- Production Package 仍保持现有离线 Fake 和服务端证据约束，本轮未扩大生产能力。

## 下一步

- 进行人工产品验收，重点确认来源标签是否足以支持创意决策。
- 后续若补充真实决策字段，应先更新数据契约和来源语义，再扩展方向卡；本轮不通过前端文案伪造能力。
