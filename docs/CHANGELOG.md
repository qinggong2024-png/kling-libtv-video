# Changelog

## 2026-10-09

### Sprint 1：上传区整理

- 根据用户再次反馈合并上传、排序、删除和大图检查，不再单列分镜序列区。
- 桌面采用素材准备与生成配置两个工作区，统一提交位于两区之后；七图换行，空态不占位。
- 模板紧凑摘要保留真实约束，配方按需打开；标准图片转视频表单保持原布局。
- 记录新的布局依据、未测量假设和 Checkpoint 1 人工验收边界；详见 `SPRINT_REPORT_VIDEO_STUDIO_UPLOAD_20261009.md`。
- testing/main build、lint 与 238/234 项单元测试通过；各 13 项 Studio、66 项页面回归、图片审核及 14 项 fixture/smoke 检查通过。最终阴影修复后 testing 受影响 make 页面追加 10 项通过。
- testing `f3a36a6` → main `d31bcde` 局部推广成功，保留生产差异，正式目录 dist 未覆盖。安全本地预览恢复，浏览器连接不可用，未声称当前标签已核查；没有正式部署或付费调用。

## 2026-10-08

### Sprint 1：布局修订

- 记录 Video Studio 任务优先级、动线、方案取舍和可测验收，明确缺少真实用户研究与效率测量。
- 改为紧凑输入侧栏 + 主生产区；移除永久源图大画布和重复缩略表示。
- 源图缩放/大图按需打开；保留分镜拖拽、键盘移动、删除、批量只读检查与提交安全边界。
- 增加四视口布局几何、结果数控件、按需检查和焦点恢复验收；详见 `SPRINT_REPORT_VIDEO_STUDIO_LAYOUT_20261008.md`。
- 实际浏览器检查补修 1102px 付费摘要挤压，加入中间宽度及付费说明可见性断言；测试/生产分支最终 11 项 Studio、10 项受影响页面回归均通过。
- testing/main build、lint 与 236/232 项单元测试通过；本轮各完成 66 项全页面回归和图片审核检查。代码分两次 scoped promotion 同步，保留生产差异，正式目录 dist 未覆盖。
- 安全本地预览已恢复，用户当前页已确认；正式服务没有部署或重启。
- 仍停在 Checkpoint 1；不扩展其他工作区，不将布局门禁等同于人工方向验收或上线批准。

### Sprint 1：Video Studio

- 实现 Canvas 优先的 Video Studio、模板选择/配方、分镜排序、队列、结果和任务抽屉。
- 新增可复用 UI/素材/模板/分镜/任务组件与六态展示适配，不替换后端状态和交付语义。
- 修复重复提交、未知提交禁用、批量约束和部分失败后成功组重复创建的风险。
- 增加模板读取恢复、嵌套视频 Modal、真实设置时长和来源 ID 保留。
- testing build/lint、234 项单元测试、10 个 Studio 浏览器用例通过；既有 66 个页面回归及图片审核检查通过。
- 新增隔离 fixture 和本地安全预览入口；不调用真实 Provider，不加载 .env，不代理请求。
- main 已同步并独立通过 build/lint、230 项单元测试、10 个 Studio 流程、66 个页面回归及图片审核检查；保留生产差异，构建产物存放在外部验证目录。
- 源码提交 testing `70b90cd` → main `e3ae81d`；详见 `SPRINT_REPORT_VIDEO_STUDIO_20261008.md`。
- 当前停止在 Checkpoint 1，等待人工方向确认；未扩展其余三个工作区。

### Added

- 固化《衣影工坊 AI Creative Studio》V1 产品范围与产品原则。
- 固化 `/studio/image`、`/studio/video`、`/tasks`、`/library` 四个产品工作区。
- 固化 Video Studio → Image Studio → Task Center → Library 的开发顺序。
- 固化 Design Token、基础组件、业务组件和 Canvas 优先的视觉规则。
- 固化生成状态的六态展示模型，并明确它不替代后端真实 phase、审核和交付状态。
- 固化组件、页面、浏览器、响应式和可访问性 QA Checklist。
- 记录当前 React + TypeScript + Vite 项目的 KEEP / ADAPT / DEFER 技术决策。
- 新增项目技术审查报告和 Sprint Report，并在 AGENTS.md 固化开发前阅读与人工检查点。

### Not Changed

- 未改动后端 API、数据库、Provider、计费、认证或状态机。
- 未把当前生产导航强行迁移为新的 URL 路由。
- 未同步 `.env`、运行时状态、缓存、构建产物或未跟踪压缩包。
- 未把 `Generated`、`Technical PASS` 或 Provider 成功提升为 `Deliverable`。

### Next

- Sprint 0：统一基础 UI 导出、状态展示映射和页面验收 fixture。
- Sprint 1：实现并验收 Video Studio + Design System。
- Checkpoint 1：人工确认 Video Studio 方向。

### Verification

- testing：build/lint 通过，31 个测试文件、209 项测试通过。
- main：build/lint 通过，32 个测试文件、205 项测试通过；构建产物在外部验证目录。
- 规范已从 `codex/testing` 局部推广至实际 `main` 目录，并检查文档一致性；不代表线上发布或页面完成。
