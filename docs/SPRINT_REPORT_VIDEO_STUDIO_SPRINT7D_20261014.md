# Sprint Report：Sprint 7-D Video Studio Desktop UI Migration

日期：2026-10-14
范围：Video Studio Desktop 展示层；1440×900、1024×768
正式入口：http://192.168.30.126:5173/

## 完成

- 1440px 待处理任务保持横向、结果保持三列；1024px 任务改为纵向列表、结果改为两列。
- 完整任务标题换行，操作按钮与文字分区；未用裁切隐藏任务内容。
- 提交区域按数量、时长、预计结果、开始生成排序；1024px 摘要和 CTA 各占一行。
- 主标题统一为“视频工作室”，Video Studio 作为辅助标题。
- 上传、配置、提交、任务和结果区域使用既有 Foundation 宽度、间距、边框和圆角 token。
- 维护提示为“暂时无法开始生成 / 已有任务仍可查看”；加载为“正在加载配置”，错误优先展示。
- 已有反馈静态文案调整为“反馈已记录”；未新增学习能力。

## 修改

- `frontend/src/features/task-center/HomeView.tsx`：标题及待处理任务内容的局部 class。
- `frontend/src/features/production/ProductionComposer.tsx`：配置加载、错误和维护文案，预计结果标识。
- `frontend/src/features/production/ResultCard.tsx`：已记录反馈的静态文案。
- `frontend/src/features/production/videoStudio.css`：桌面任务布局、结果列数、操作区换行。
- `frontend/src/features/production/studioRefinement.css`：桌面提交 grid 与局部 Foundation 收敛。
- `frontend/src/features/video-studio/VideoStudio.browser-check.mjs`：独立隔离桌面验收。
- `scripts/ui-video-studio-check.mjs`：同步新标题、明确拖拽位置、允许指定已有 Chrome。
- `scripts/ui-studio-refinement-check.mjs`：同步 Foundation 240px sidebar 断言、允许指定已有 Chrome。
- 本报告：记录结果与限制。
- 开发顺序：Commit 1 `1b560e1` 修复任务与结果；Commit 2 `8fddcf2` 整理提交与状态；Commit 3 收敛标题和 token、完成回归与报告。
- 未修改 AppShell、全局 styles.css、API、后端、Provider、Workflow、Prompt 或业务状态。
- 对照开发基线确认 ProductionComposer 渲染前逻辑、CTA handler/disabled 条件和 ResultCard 渲染前处理函数一致；HomeView 仅添加展示 class 和替换标题。
- 保留 `.app-shell--video`；新增 CSS 使用 `.video-studio` / `.composer--studio` 局部作用域，不扩展独立 Shell。

## 测试

- codex/testing：build、lint 通过；Vitest 60 文件 / 417 项通过。
- codex/testing 桌面专项：1440px 41 项、1024px 43 项通过；无横向溢出、文字按钮重叠、外部网络请求或生产写入。
- codex/testing 已有视频回归：13 个隔离场景全部通过；已有 refinement 回归：4 个场景通过。
- main 实际工作目录：lint 通过；桌面专项 41/43 项通过；已有视频回归 13 个场景全部通过。
- main 实际工作目录全量 build 未通过：并行任务新增 AI 配额文件，但 `getAIQuota` / `AIQuota` 接口与类型尚未齐全。
- main 实际工作目录全量单测：60 文件通过、1 文件失败；409 项通过、4 项失败，均为 `api.aiUsage.test.ts` 的 `getAIQuota` 缺失。
- 补充隔离验证：导出 main 已提交基线，仅应用本轮限定补丁，不带入其他未完成改动；build、lint、59 文件 / 404 项单测通过。这不等于实际 main 全量验收通过。
- 浏览器仅访问隔离 fixture；旧回归的创建、未知提交和拒绝响应均为合成数据，没有调用真实 Provider 或付费生成。
- 验证上传、素材排序与删除、七张上限、配置与 CTA、任务可读性、结果列数、错误/维护、刷新恢复、返回导航。
- 刷新后按原规则恢复配置，浏览器 File 不自动恢复；未改变恢复行为。
- 构建产物、截图、fixture 和缓存保存在仓库外 `E:/Codex/video-studio-sprint7d-evidence/`，未覆盖正式 dist。
- testing 与 main 的八个源代码/测试文件在规范化行尾后相同；同步仅包含本轮文件与报告，其他脏改动保留。

## 发现问题

- 跨工作区 Creative Shell 扩展回归未通过：素材库选择器等待失败、移动 Director CTA 遮挡断言失败、任务列表滚动恢复超时。本轮未修改这些区域，未宣称全工作区验收通过。
- 初次旧视频回归仍使用旧标题，且 1102px 默认中心拖拽偶发落点失败；修正标题和拖拽位置后，两侧 13 场景全部通过，未改变上传或排序业务逻辑。
- main 并行 AI 配额开发未闭合，仍阻断实际工作目录全量 build 和四项单测；本轮没有同步其 API/类型或修复该功能。
- 本轮只验证 Desktop；旧脚本包含移动回归，但没有进行移动端设计迁移。
- 真实视频生成、付费、Provider 可用性和线上服务恢复不在本轮验收范围。

## 下一步

- 人工确认 Video Studio Desktop 信息层级与操作路径。
- AI 配额任务完成后，重新执行实际 main 全量 build 与单测。
- 跨工作区回归失败单独归属素材库、导航和恢复任务，不并入本轮视频展示层。
- 源码同步不等于部署；未推送远程、重启服务、迁移数据或启动真实生成。
