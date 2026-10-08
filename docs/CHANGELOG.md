# Changelog

## 2026-10-08

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
