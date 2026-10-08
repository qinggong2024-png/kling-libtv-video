# Sprint Report：V1.0 规范冻结

日期：2026-10-08
本轮范围：开发合同落地和技术审查；未开始 UI 实现 Sprint

## 完成

- 产品范围、页面结构、设计语言、组件体系、开发顺序固化为 V1.0。
- 保留 Video Studio + Design System 首先交付和两个人工检查点。
- 完成代码结构、API、数据库模型、配置样例和既有测试证据审查。

## 修改

- 新增 PRODUCT_SPEC、DESIGN_SYSTEM、DEVELOPMENT_PLAN、QA_CHECKLIST、CHANGELOG。
- 新增 TECHNICAL_AUDIT_20261008 和本报告。
- AGENTS.md 增加开发前强制阅读、角色边界、验证与交付规则。
- 未修改前后端业务逻辑、依赖、真实 .env、数据库或运行服务。

## 测试

- codex/testing：build 通过，lint 通过，Vitest 31 文件 / 209 项通过。
- main：build 通过，lint 通过，Vitest 32 文件 / 205 项通过；build 输出至外部验证目录，未覆盖正式目录 dist。
- 两侧结果分别记录，不把 209 项测试结果宣称为 main 的测试结果。
- 文档推广成功：规范提交 testing `3bfb563` → 实际生产目录 main `52e11ee`，只推广本轮八个文件。
- 七份文档 Git blob 哈希一致，AGENTS 新增 V1.0 段一致，保留生产目录既有差异。
- 两目录的基线到推广后 diff 只包含 AGENTS 与本轮文档；main 干净，testing 仅保留用户未跟踪 ZIP。
- 格式检查已修复 Markdown 行尾空格；`git diff --cached --check` 通过。
- 浏览器：本轮不执行，文档修改不构成页面验收；既有证据仍有其限定范围。

## 发现问题

- 现有仓库使用 React/Vite 和 query-view 导航，不能把技术建议当作强制重写。
- 六态展示需要保留 UNKNOWN、CANCELLED、待审和部分完成，不覆盖后端真实 phase。
- 旧环境文档正式入口与本次用户/AGENTS 不同，以后者 5173 为准。
- 两个目录 Git 元数据不同，main 推广必须检查实际生产目录。
- QA 初稿 smoke 命令执行目录不正确，已修正；smoke 不能证明完整生成链。
- 代码同步不等于在线部署；本轮未推送远程、重启服务或改动生产数据。

## 下一步

- 实际开发从 Video Studio + Design System 开始，不同时开发四个页面。
- 仅提取首个生产流程所需共享组件，并保留历史挂载、通知、导航和 API 语义。
- 使用隔离 Playwright fixture 验证选择素材、选择模板、创建任务、观察状态和查看结果。
- Checkpoint 1 由产品负责人确认方向；线上发布和真实付费验证单独处理。
