# Sprint Report：Director Studio V2 Sprint 3

日期：2026-10-13
本轮范围：Creative Direction 前端展示层；将方向选择卡升级为创意决策卡

## 完成

- 将 `Direction Card` 扩展为标题、Creative Summary、Execution Concept、Visual Proposal、Information Source 和选择状态。
- 将已有 `scene`、`behavior` 标为 `AI Result · 离线 Fake`，摘要标为前端结果整理，不称为完整创意策略。
- 将名称及已有 `camera`、`emotion` 标为本地 `Creative Proposal · 创意提案`。
- `Information Source` 使用卡片内的折叠详情，区分 AI Result、Creative Proposal、User Input 和 Unknown；用户输入只说明实际请求使用的商品图与品牌归属。
- 缺少的目标受众适配、商品证据和取舍风险明确显示“未提供”，不生成对应字段。
- 移除独立的“方向差异对比”区域，避免 scene / behavior 重复展示。
- 保留点击选择、确认调用 `select_direction`、确认后锁定和 Production Package 原有流程。
- 桌面端保持三张等宽方向卡，移动端改为纵向排列。
- 选择动作上移到摘要后；摘要及执行文本限制展示高度，长内容可滚动读取，来源详情默认收起。
- 查看来源不改变选择状态；名称、摘要、选择动作使用按钮供键盘操作，点击卡片执行信息也仅更新本地选择。

## 修改

- `frontend/src/features/director-studio/DirectorStudio.tsx`
- `frontend/src/features/director-studio/DirectorPlanningViews.tsx`
- `frontend/src/features/director-studio/directorPresentation.ts`
- `frontend/src/features/director-studio/directorStudio.css`
- `frontend/src/features/director-studio/directorPresentation.test.tsx`
- `frontend/src/features/director-studio/DirectorStudio.browser-check.mjs`
- `docs/CHANGELOG.md`
- 本报告

未修改后端 workflow、`select_direction`、Agent、方向生成逻辑、Provider 或 Production Package 数据结构。

## 测试

- testing：build、lint 通过；Vitest 56 个测试文件 / 397 项通过。
- main：build、lint 通过；Vitest 57 个测试文件 / 393 项通过。最终 main build 输出至外部证据目录。
- 两侧独立的隔离 Director Playwright fixture 通过：1440、1024、768、390 四个视口均通过，各视口 18 个既有 Fake 命令。
- 浏览器流程验证点击方向不创建 Production Package，确认方向后只发送一次 `select_direction`，后续 Fake review、刷新、选择和 storyboard 流程通过。
- 额外验证来源详情不触发选择、键盘 Enter 选择、确认后返回 Creative Direction 不能切换方向且旧包仍保留。
- 390px 通过元素实际坐标验证方向名称、核心摘要和选择动作均位于 844px 首屏内；卡片纵向排列，页面无横向溢出。
- 1440、1024、768 下三张卡等宽同排，默认高度不超过 560px；四视口截图完成复核。
- 浏览器 fixture 阻断外部请求；首次默认 Edge 不存在，改用本机 Chrome 显式路径完成验证。
- 最终证据：`E:/Codex/director-v2-sprint3-final-testing-20261013` 与 `E:/Codex/director-v2-sprint3-final-main-20261013`。
- scoped 源码同步到 main，保留既有分支差异；没有同步环境文件、缓存或浏览器截图，没有推送、服务重启或线上部署。

## 发现问题

- 当前服务端方向接口仍只提供 `id`、`scene`、`behavior`；summary 在现有前端映射中由这两个字段组成。
- 名称、`camera`、`emotion` 仍来自已有前端规划参考，已明确标记为创意提案，不能视为 AI 分析证据；`human` 未新增到卡片。
- summary 与 scene / behavior 在现有映射中仍有语义重合；本轮按约束保留已有 summary，删除的是卡片之外的重复对比和 DNA / Reality 摘要区域。
- 当前没有真实的 Target Audience、Product Evidence 或 Trade-off 数据，界面只显示 Unknown 说明。
- Production Package 仍保持现有离线 Fake 和服务端证据约束，本轮未扩大生产能力。
- 浏览器检查使用合成数据与隔离网络，不能替代真实后端联调、完整应用外壳验收或正式人工验收；现有恢复代码未修改，fixture 覆盖状态刷新，没有新增项目重载恢复验收。

## 下一步

- 进行人工产品验收，重点确认来源标签是否足以支持创意决策。
- 后续若补充真实决策字段，应先更新数据契约和来源语义，再扩展方向卡；本轮不通过前端文案伪造能力。
