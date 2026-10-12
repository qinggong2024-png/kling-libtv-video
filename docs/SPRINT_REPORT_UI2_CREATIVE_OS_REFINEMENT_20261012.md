# Creative OS UI-2 Refinement Report

日期：2026-10-12
阶段：Milestone UI-2 / High Fidelity Design Refinement
范围：前端产品壳、项目上下文、导演台布局、Studio 视觉一致性。
状态：工程验证完成；停在人工体验验收。

## 1. Design Architecture

完成：

- 收敛为连续制作工作台，桌面导航 208px，内容区上限 1120px。
- 沿用 React / TypeScript / Vite、Lucide 和现有语义 token，不引入 UI 框架或运行依赖。
- 使用中性浅色背景、紧凑字重层级、蓝色行动焦点，素材保留自身颜色。
- 工作区区块改用留白与分隔线，去除层层卡片和重复标题。
- 保留授权、审核、未知结果、Fake / 不可交付等真实语义。

详细设计约束见 `UI2_REFINEMENT_SPEC_20261012.md`。

## 2. Navigation Structure

主入口：图片工作室、视频工作室、任务中心、素材库。

智能导演是图片工作室内模式。项目、记忆和工作区从一级导航移除，兼容深链接和页面能力保留。项目上下文条只提供一个当前项目入口；工作区自身不再重复显示上下文条。

管理入口仍依现有角色权限展示。设置、帮助、账号和移动端设置保留。移动端使用一套底部导航，不再叠加八项横向产品导航。

未修改 `useAppNavigation.ts`。旧 `?view`、`?task` 与 pane 链接继续工作，`?project` 导航引用保留。主导航任务中心复用原来的全部任务入口，工作区审核步骤保持 review / attention 行为。

## 3. Page Changes

修改：

| 文件 | 本次变更 |
| --- | --- |
| `frontend/src/app/App.tsx` | 四个主导航名称；移除第二套产品导航配置；减少项目上下文重复 |
| `frontend/src/app/AppShell.tsx` | 单一导航；管理入口放入辅助区域；Studio 模式正确高亮其所属工作区 |
| `frontend/src/features/creative-workspace/CreativeWorkspaceView.tsx` | 项目名作为主标题；下一步前置；图标编辑和规划记录入口；保留原有派生状态 |
| `frontend/src/features/image-studio/ImageStudio.tsx` | 图片工作室标题；导演模式不再显示属于批量图片草稿的保存标签 |
| `frontend/src/features/director-studio/directorStudio.css` | 三栏 / 两栏 / 纵向适配；输入和预览统一；序号不换行 |
| `frontend/src/styles.css` | 壳层语义颜色、控件、导航、工作区与图片页视觉统一 |
| `scripts/ui-smoke.mjs` | 标题断言随“图片工作室”文案更新，原有检查保留 |

新增：

- `scripts/ui-creative-shell-check.mjs`：使用现有隔离 fixture，加载真实 main.tsx / CreativeProjectProvider，验证壳、响应式、项目编辑、历史导航和任务详情。
- `docs/UI2_REFINEMENT_SPEC_20261012.md`：保存 UI-2 方向、尺寸、路由兼容与验收边界。
- 本报告。

其他窗口的 DirectorStudio 恢复、ProductionComposer、Provider、后端和合同改动没有夹带进本次源码提交。

## 4. Design System

- 复用现有 Button / IconButton、Drawer、状态 Badge 和 Creative 组件。
- 新增/调整的常用操作至少 44px，图标编辑和记录按钮带名称及 tooltip。
- 字距为 0，固定字号；长项目名称换行，上下文条名称明确截断。
- 导航使用约 120ms 颜色反馈，取消导航位移和大面积按钮阴影。
- 工作区步骤不使用卡片堆叠；已记录证据与生成进度、交付资格分开呈现。
- 新样式尊重 reduced-motion，沿用既有浮层交互与忙碌状态 guard。
- 不通过新增展示状态重定义 Task State 或 Workflow Phase。

## 5. UX Flow

当前项目 → 下一步 → 图片工作室内智能导演 → 商品输入 → 方向候选 → 生产包 → 图片 / 视频制作 → 任务中心审核。

验证：

- 工作区下一步在四个目标视口首屏内可达。
- 项目编辑关闭后恢复触发按钮焦点。
- 工作区不与可见 Video Studio 堆叠。
- 离开图片页后 ImageStudio 仍挂载并隐藏，后台轮询/通知的结构约束保留。
- 导演属于图片工作室，模式切换不新增全局入口。
- `?task=id` 打开详情抽屉；records → 详情 → Escape 返回恢复实际滚动位置。
- back / forward、长名称、旧页面及项目/记忆 pane 刷新通过。

以上是自动化操作证据，不代表已测量新员工理解时间或真实人工制作效率。

## 6. Validation

测试：

| 验证 | codex/testing | 实际 main |
| --- | --- | --- |
| build | 通过，输出仓库外 | 通过，输出仓库外 |
| lint | 通过 | 通过 |
| unit tests | 52 文件 / 322 项通过 | 53 文件 / 317 项通过 |
| npm run smoke:ui | 9 个页面通过 | 9 个页面通过 |
| 壳与导航 | 4 个视口 + 任务/滚动案例通过 | 同样 5 个案例通过 |
| 既有视频流程 | 13 项通过 | 13 项通过 |
| 既有导演离线流程 | 1440 / 390 通过 | 1440 / 390 通过 |
| 导演恢复边界 | 无效引用清理、网络失败保留通过 | 相同 2 项通过 |

壳检查视口：1440×900、1024×768、768×1024、390×844。

浏览器：Chrome 155.0.8059.39。机器未安装现有旧脚本默认指定的 Edge；使用仓库外 Playwright launch 适配器指定已安装 Chrome，未删改流程断言。

发现问题及修复：

- 导演三栏下序号 `01` 发生换行：增加不可收缩 / 不换行约束并重新验收。
- Smoke 仍期待旧标题“图片中心”：只更新标题预期，重跑两侧全部 9 页面通过。
- 测试桩入口最初使用错误的页面 selector：修正为仓库现有 `.records-overview` / `.content-library-view`，不是修改生产页面以迎合测试。

证据根目录：`E:/Codex/ui2-20261012/`。

最终壳证据：`testing-shell-final/report.json`、`main-shell/report.json`，含源码 SHA-256 与截图。其他结果位于 `testing/main-smoke`、`testing/main-video`、`testing/main-director`。视频结果文件名为 `result.json`，导演结果为 `report.json`。

源码同步：

- 测试源码提交 `504200a3121a423bf89e480d3c8477418ecc577c`。
- 实际 main 对应提交 `17038b0a8c1847fa420eeb4fe4f7c40691c515a8`。
- 只 cherry-pick 本次 9 个文件的补丁，未将测试分支全树覆盖 main。
- 两侧本次源码文件干净、Git blob 一致；各自其他未提交工作继续保留。
- 测试在各自当前工作树执行；其他窗口的未提交功能存在，不冒称为全部隔离提交快照验收。测试数量差异来自既有分支差异。

## 7. Remaining UI Improvements

发现问题 / 限制：

- 当前本地 5174 页面仍显示 backend proxy 502；本轮隔离浏览器通过不代表修复正式运行环境。
- 导演运行流程回归使用既有独立 Director / HomeView fixture；完整 App 壳验证覆盖导演输入布局，未声明真实服务端生成结果已通过三栏体验验收。
- CreativeProject 仍是既有本地项目上下文；本轮不新增后端项目列表、项目创建 API 或多项目数据模型。
- 未进行真实 Provider、付费生成、正式素材审核写入、数据库迁移、部署或服务重启。
- 最终视觉成熟度、创意人员实际操作效率和上线批准仍由人工接受。
- 生产包的长 Prompt、密集候选审核和大量素材仍可在真实授权样本到位后继续细化；不得将 Fake 或默认参考冒充真实素材质量。

## 8. Recommendation

下一步：

先人工体验当前工作区和图片工作室内导演模式，确认入口数量、密度和三栏布局。之后只根据具体体验反馈继续 UI 细化。

本阶段停止，不自动进入真实 Provider Bridge、Billing、AI 能力扩展或部署。后续若涉及架构边界、数据模型或生产流程变化，先提交明确方案并等待决策。
