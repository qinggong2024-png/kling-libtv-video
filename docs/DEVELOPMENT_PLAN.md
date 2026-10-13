# 衣影工坊 V1 开发计划

版本：V1.0
日期：2026-10-08
状态：开发顺序冻结

2026-10-13 当前增量排程以 `CREATIVE_CORE_HUMAN_LOOP_20261013.md` 为准：
Creative Package → Brand DNA → Human Review → 人工测试。
暂停新增 Agent、State 扩展、Provider 深度改造和 CreativeTask 全量迁移；
以下 V1 历史计划及人工检查点保留，不代表已经完成或接受。

2026-10-10 Creative Workflow 增量任务书见 `CREATIVE_WORKFLOW_IMPLEMENTATION_20261010.md`。本次先冻结后端合同与开发包，不把规范更新当成功能实现或人工方向接受。

2026-10-11 内部 MVP 交付策略见 `INTERNAL_MVP_DELIVERY_PROFILE_20261011.md`。该策略只降低验证复杂度和发布等待，不删减 Creative Workflow 任务书中的功能范围。

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
  └── Upload + Storyboard（同区整理）
→ TemplateSelector
→ CreativePanel / 按需 SourceInspector
→ GenerationPanel
→ ResultGallery
```

最小可用流程：

1. 选择产品和其他源素材；
2. 选择模板；
3. 在上传区完成分镜排序、删除与按需放大检查，不跨区整理素材；
4. 配置生成意图与必要生产参数；
5. 创建视频任务；
6. 感知 queued / preparing / running / validation / completed / failed；
7. 在结果区查看并进入审核或交付路径。

Checkpoint 1：人工确认方向正确后，才扩展其他页面。

当前布局修订遵循 `VIDEO_STUDIO_BANDS_REVIEW_20261009.md`：此前左右结构仍被用户否定，改为纵向素材、创意、提交三个操作区；主体按需展开，输入状态保留。用上传区排序/删除/检查、主体键盘展开与收起保留、七图适配、首屏提交及结果入口坐标验收。此前两份布局方案保留为历史。工程门禁不替代产品研究或人工易用性验收；全站视觉方向原型不在本轮采用范围。

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

## 8. Creative Workflow 开发包

2026-10-10 后续用户决定：先整体骨架，再单正面 Fake 闭环逐段测试。前置门分为隔离开发/真实验证/上线，批准 CW-1 离线首包；下文旧的“未通过不推进 CW-1”是前置调查时点记录，不阻塞已授权的隔离实现。真实调用/预算/许可/Critic/质量目标仍待独立验证，前端仍等待 Checkpoint 1。

不重构既有生产系统，采用以下依赖顺序：

```text
CW-0.5 八项立项前置评审 / 基线及采样计划
→ CW-1 持久素材 / Grounded DNA / 状态与 attempt / 循环授权 / shot_id / 隔离迁移
→ CW-2 按模块分析 / A-B-C 差异 / 内容库快照 / Prompt Registry / Preservation / 生产包
→ CW-3 首帧 / 像素 Critic / 有界真实性循环 / 背面确认 / 分镜 / 人工审核选择
→ CW-4 director_fixed 视频两模式 / 服务端素材复用 / 子任务恢复与兼容证明
→ CW-5 导演前端与隔离浏览器闭环
```

后端合同与隔离验证先行，不代表获准扩展前端。CW-5 及其他工作区的前端扩展仍等待 Checkpoint 1 接受；智能导演在 Image Studio 内，不新增 `/director`。

每包开工前给出实际文件、API、两侧迁移基线和回归范围。CW-3 必须适配商品单图输入，不绕过旧 model.front 约束；CW-4 必须绕开现有自动 Prompt 重新规划，但保留旧客户端及已提交任务恢复。

缺背面使用用户确认的无印花纯色假设，人工品牌选择覆盖模型猜测。内容库、原商品图及已审核分镜采用服务端持久引用，不能依赖重复用户上传。

每包在 testing 验证后推广同一局部改动至实际 main，迁移只验证隔离数据库，不自动发布服务或调用付费 Provider。预算、生成命令路由和历史 API 兼容策略前移到 CW-0.5 冻结，不边接 Provider 边猜合同。

CW-0.5 的 CW-P01 至 CW-P08 分别交付：两侧能力矩阵、持久素材/镜号映射、完整状态/动作/恢复合同、分析/规划/复核/媒体预算与循环授权、事实/方向/Prompt 真源、许可/降级表、迁移 heads/旧模式隔离计划、指标阈值/基线/独立授权采样计划。2026-10-10 已形成 `CREATIVE_WORKFLOW_PREFLIGHT_20261010.md` 与离线检查证据，实际立项评审未通过。

入场 testing HEAD `a9db2d6` / head `c8d4e6f1a203`，实际 main HEAD `4cc509f` / head `c9f0a1b2c304`。main 已有商品基础与两个额外迁移；先评审窄范围回移/对齐，再在统一 head 上增加 Creative 迁移。禁止重复建 Product 或从 testing 旧 head 直接推广新迁移。

前置待决 D01 至 D06 包含 Product 对齐、真实价格/预算、许可/SKU、质量目标、Critic 能力及 PG/带数据兼容验证；详细责任和候选目标见评审包。现有 SQLite 空库升级与 Fake PASS 不替代它们，不推进 CW-1。

插件规则按 v1.13.5 归一化，27 > 26 > 24 > 23 的解释优先级覆盖旧比例和先图后方案顺序；执行阶段按任务书 12.2 顺序，Reality 内部按 Camera→Lighting→Composition→Human Behavior→Environment→Imperfection。不是机械按文件编号运行，也不是每模块都必须独立付费调用。

CW-2 用 Fake/Replay 验证六维具体工件、锁项优先、参考安全/证据、Prompt Preservation 和不可变版本；CW-3 验证真实像素复核 schema、失败定向修订、新包/候选和人工资格分离。循环默认关闭，启用默认每稿 1 次修订、首版硬上限 2 次，总任务预算/授权有效期/停止规则逐调用检查，多 worker 不重复提交。

循环修改走导演新版本编译，不在图片/视频提交时改 Prompt；只回失败涉及模块并重检下游，不重做方向或改变锁项。缺原图/输出像素、模型不能复核、UNKNOWN/WRITE_UNCERTAIN、连续无改善或预算耗尽时停止；已提交调用继续查询/结算。外部摄影自动检索是可选适配，首版可用已授权素材及 DNA_only，不另建站点分析系统。

CW-4 必须以 spy/负断言证明 director_fixed 不调用 compile_video_plan/apply_video_learning；关联断裂、一次性上传桥接、哈希/审核撤回、shot_id 排序及崩溃恢复覆盖后才能开放入口。CW-A01 至 CW-A30 是待执行标准，不继承既有 Studio 通过结果。

工程 Fake/Replay 与真实质量 A/B 分开。至少一个有权 SKU 设计对照，真实调用单独授权；记录首帧/分镜合格率、真实性缺陷率、人工分钟、重复上传/提交、总成本、循环次数/停止原因及未核验比例，阈值由产品负责人在 CW-P08 接受，不用小样本承诺所有商品改善。
