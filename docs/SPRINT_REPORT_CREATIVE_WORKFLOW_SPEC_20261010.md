# Sprint Report：Creative Workflow 开发合同修订

日期：2026-10-10
范围：根据用户确认修正 Implementation Specification，不是功能开发 Sprint

## 完成

- 定义正面单图分析、背面纯色假设、导演 DNA 和人工品牌选择。
- 定义内容库快照、图片/分镜审核选择、视频两模式和服务端素材复用。
- 固化逐包开发、文件/迁移/API 变化及 CW-A01 至 CW-A15 验收矩阵。
- 保留四个工作区、Checkpoint 1、既有生产门禁及历史任务兼容。

## 修改

- 新增 `CREATIVE_WORKFLOW_IMPLEMENTATION_20261010.md` 与本报告。
- 局部更新 `PRODUCT_SPEC.md`、`DEVELOPMENT_PLAN.md`、`QA_CHECKLIST.md`、`CHANGELOG.md`。
- 未修改前后端源码、依赖、AGENTS、旧验收记录、真实配置或生产运行数据。
- 入场 testing 为 `27fbcee`，实际生产目录 main 为 `b5c4f99`；两侧有用户既有未提交改动，保留不动。
- 测试仓库记录的 main/worktree HEAD 不能替代实际生产目录 HEAD，本轮以实际目录为准。

## 测试

- testing/main 各 42 项文档规则、JSON 示例、格式和引用检查通过；CW-A01 至 CW-A15 共 15 条标准存在且未标为已执行。
- 两侧本轮四份既有文档在入场时内容一致；使用局部补丁同步，另两份新文档逐文件推广，不覆盖整棵生产树。
- 六份文档规范化换行后内容一致；两侧目标文件 `git diff --check` 通过。Git 仅提示部分 LF 后续将转换为 CRLF，未报告格式错误。
- 基线文件 SHA-256 检查：testing 本轮范围外 545 个文件、main 范围外 534 个文件均未变化，既有未提交 UI/文档/压缩包保留。
- 文档已成功同步到实际 main 工作区；本轮没有提交或推送 Git，不声称两侧工作区干净。
- 本轮不执行 build/lint/unit/browser：只有文档变更，不更新任何功能验收状态。
- 不读取真实 .env，不连接生产数据库，不迁移、重启、部署或调用付费 Provider。

## 发现问题

- 现有生图 fusion/storyboard 均要求 model.front + product.front；单商品导演输入须单独适配。
- 现有视频 automatic 会重新编译 Prompt 并应用学习指导；导演自动执行必须显式隔离该路径。
- 一次性 StagedUpload 与浏览器 File 不足以保证跨阶段素材复用；需真实服务端引用、保留策略和来源检查。
- 缺背面的无印花纯色是已允许的用户假设，不是实物事实；审核不得声称比对过未上传背面。
- Checkpoint 1 仍未接受，本轮不扩大前端实施范围；品牌资料与插件团队知识需先核实公开传播许可。

## 下一步

- 按 CW-1 审查实际两侧迁移图、素材/库能力和共享安全边界，输出最终文件清单。
- 首个代码包冻结分析/规划模型预算、生成路由、旧客户端兼容和素材保留合同。
- 先隔离实现后端合同与生产包，再分包接图片/视频；前端扩展等待 Checkpoint 1。
- 每包 testing 验证后局部推广 main，真实生成与部署仍需单独授权。
