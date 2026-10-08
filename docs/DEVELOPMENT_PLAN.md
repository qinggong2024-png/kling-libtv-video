# 衣影工坊 V1 开发计划

版本：V1.0
日期：2026-10-08
状态：开发顺序冻结

## 1. 当前技术审查摘要

审查分支：`codex/testing`
当前前端：React + TypeScript + Vite
UI 图标：`lucide-react`
验证脚本：

```text
npm run build
npm run lint
npm run test
npm run smoke:ui
```

已存在并应优先复用：

- `frontend/src/app/App.tsx`：应用壳、导航、认证边界和全局通知；
- `frontend/src/app/useAppNavigation.ts`：现有 URL 状态、详情返回和任务深链接；
- `frontend/src/features/image-center`：图片生成、轮询、结果选择与审核相关能力；
- `frontend/src/features/production`：视频制作工作区、素材、提示词、结果和轮询；
- `frontend/src/features/task-center`：首页、任务记录和任务详情；
- `frontend/src/features/library`：内容库；
- `frontend/src/shared/components/ui.tsx`：现有共享 Drawer、Alert、EmptyState 等基础组件；
- `frontend/src/domain`：状态机和展示映射；
- `frontend/src/api.ts`：后端 API 类型化客户端。

当前缺口：

- 尚无独立的 `frontend/src/shared/components/ui/` 组件目录；
- 业务页面仍以历史 view 名称组织，尚未完全映射为四个产品工作区；
- 后端真实 phase 多于产品展示六态；
- Video Studio 的模板、Storyboard、Canvas、Result Gallery 还需要统一成完整工作流；
- 已有离线页面和图片审核浏览器证据，但整体验收、性能和完整生成链仍未完成；参见 `runbooks/ui-pages-acceptance-20261008.md`。

详细审查见 `TECHNICAL_AUDIT_20261008.md`；本次 Sprint Report 见 `SPRINT_REPORT_20261008.md`。

## 2. 适配决策

| 项目 | 决策 | 原因 |
| --- | --- | --- |
| React + TypeScript + Vite | KEEP | 当前构建、测试和页面拆分已经稳定 |
| 现有 API / domain / 状态机 | KEEP | 保护幂等、审核、交付和可靠性语义 |
| 现有共享 `ui.tsx` | ADAPT | 逐步形成统一导出，避免重复基础组件 |
| Next.js / Tailwind / shadcn 全量迁移 | DEFER | 本阶段没有足够收益，且会扩大回归面 |
| 独立四页面产品结构 | ADAPT | 通过现有导航兼容入口渐进迁移 |
| 产品六态展示模型 | ADAPT | 只作为 presentation 层，不替代后端状态 |

## 3. Sprint 顺序

### Sprint 0：合同与基础组件

目标：

- 读取本目录五份规范和既有 L1-L4 合同；
- 固化 token、基础组件导出和状态展示映射；
- 建立页面验收 fixture 与截图命名规则。

验收：

- 共享按钮、输入、Badge、Drawer、Modal、Thumbnail、EmptyState 可复用；
- 基础组件有键盘、焦点和 reduced-motion 测试；
- 不改变现有生产 API 和后端状态语义。

### Sprint 1：Video Studio，最高优先级

Sprint 0 只建设 Video Studio 实际需要的基础组件；其余共享组件在真实使用处提取，不先建设闲置组件库。Sprint 0 与 Sprint 1 构成同一首个视觉/交互交付单元。

目标顺序：

```text
AssetPanel
→ TemplateSelector
→ CreativeCanvas
→ Storyboard
→ GenerationPanel
→ ResultGallery
```

最小可用流程：

1. 选择产品和其他源素材；
2. 选择模板；
3. 按需放大检查源图，而非强制经过常驻画布；
4. 配置分镜或必要生产参数；
5. 创建视频任务；
6. 感知 queued / preparing / running / validation / completed / failed；
7. 在结果区查看并进入审核或交付路径。

Checkpoint 1：人工确认方向正确后，才扩展其他页面。

布局修订遵循 `VIDEO_STUDIO_LAYOUT_REVIEW_20261008.md`：先做任务定性评定和方案取舍，再实施输入侧栏 + 连续主生产区；用首屏主动作坐标、重复素材数量、顺序/删除/检查交互及响应式截图验证。工程门禁不替代产品研究或人工易用性验收。

### Sprint 2：Image Studio

复用：

- Asset System；
- Template System；
- Generation System；
- Gallery / ResultCard；
- Drawer 和状态映射。

流程：

```text
Product + Character + Scene
→ Generate Images
→ Select / Review
→ Create Video
```

必须保持“选择不等于审核通过”的现有语义。

### Sprint 3：Task Center

目标：

- FilterTabs；
- TaskQueue；
- TaskDetailDrawer；
- ReviewGallery；
- 查看、重试、局部重新生成、下载；
- 真实失败和未知结果的分流。

任务展示状态统一由 domain/presentation 层映射，不能在组件中复制判断。

### Sprint 4：Library

目标：

- Character、Product、Scene、Template 分类；
- 资源网格；
- DetailDrawer；
- 与两个 Studio 的选择器复用同一资产身份和权限语义。

Checkpoint 2：四个产品工作区完成后人工确认上线方向。

## 4. 任务 DAG

```text
Contract / Audit
    ↓
Tokens + UI Primitives
    ↓
Shared Asset / Template / Generation Components
    ↓
Video Studio
    ↓
Image Studio
    ↓
Task Center
    ↓
Library
    ↓
Browser / Responsive / Accessibility Acceptance
```

以下依赖不得绕过：

- 没有真实资产身份，不得先做结果交付；
- 没有统一状态映射，不得在四页分别实现状态颜色；
- 没有 Video Studio 验收，不并行扩展四个页面；
- 没有 API 合同，不伪造计费、审核、交付或 Provider 成功。

## 5. 文件与模块边界

推荐新增或演进：

```text
frontend/src/shared/components/ui/
frontend/src/shared/components/assets/
frontend/src/shared/components/studio/
frontend/src/shared/components/tasks/
frontend/src/shared/components/library/
frontend/src/domain/studioTaskStatus.ts
```

推荐页面边界：

```text
frontend/src/features/video-studio/
frontend/src/features/image-studio/
frontend/src/features/task-center/
frontend/src/features/library/
```

迁移旧模块时按可验证的小步进行，不删除仍被 `App.tsx`、通知轮询或深链接依赖的挂载点。

## 6. 每个开发任务的交付物

每项任务必须记录：

- 目标和影响范围；
- 输入、输出和依赖；
- KEEP / ADAPT / REPLACE / REMOVE / DEFER 决策；
- 组件、API 和状态边界；
- 自动化测试；
- 浏览器验收视口；
- 未解决风险；
- 对测试分支和生产分支的同步结果。

每轮按以下流程推进：

```text
分析 → 规划 → 开发 → 测试 → 审查 → 优化 → 验收
```

缺陷闭环：

```text
发现 → 定位 → 修复 → 重新测试 → 记录
```

每个 Sprint Report 使用以下字段：

```text
完成：
修改：
测试：
发现问题：
下一步：
```

不把付费 Provider、生产数据写入、数据库迁移或服务重启包含在普通自主开发授权内。代码同步与运行环境发布分开记录。

## 7. Stop Rule

当当前 Sprint 验收通过、没有更高价值的主线阻塞项，且继续增加组件、模型或 QA 不会明显改善生产效率或关键质量时停止扩展，进入人工检查点。
