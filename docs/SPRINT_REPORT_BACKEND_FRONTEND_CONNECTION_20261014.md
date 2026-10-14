# Sprint Report：未配置 API 的前后端联调

日期：2026-10-14

## 完成

- 根据用户最新要求暂停真实商品验收和真实生成，先修复前后端连接与恢复入口。
- 导演接口复用主 API 客户端的当前用户、Cookie、CSRF、超时及结构化错误处理。
- 已有 Workflow 的 DRAFT / ANALYSIS_FAILED 可以调用后端现有 analyze / retry_analysis；提交前重新读取服务端版本。
- Product 创建成功、Workflow 创建失败后，同一页面重试复用已有 Product；已存在 Workflow 的分析重试不创建新 Product / Workflow。
- API、Worker 使用同一隔离数据根；Safe 不读取项目真实 .env，不继承 Provider 密钥，不加载已有 Provider 配置。
- 建立独立、零费用的前端 API 联调入口。未修改 Workflow、Creative State、Provider Executor、数据库结构或 UI 布局。

## 修改

两侧同步的本轮文件：

- frontend/src/api.ts：只新增共享 request 导出，保留 main 独有 Product API 等差异。
- frontend/src/features/director-studio/directorApi.ts
- frontend/src/features/director-studio/directorApi.test.ts
- frontend/src/features/director-studio/DirectorStudio.tsx：只修复调用及失败恢复；保留其他任务的上传 UI 变更。
- frontend/src/features/director-studio/DirectorStudio.browser-check.mjs
- backend/src/libtv_agent/runner/local_runner.py
- backend/tests/test_local_runner.py
- scripts/start-test-stack.ps1：增加 DataRoot、Safe 隔离、保护端口及 Windows 引号修复；main 保留原有 Full 配置行为。
- scripts/ui-backend-integration-check.mjs
- 本报告及 CHANGELOG。

main 另外修正 backend/tests/test_phase2_evidence_scripts.py 的过时断言。testing 已有相同的有效 app-dir 检查，保留其原有说明。

## 数据流

前端主客户端 → 当前认证上下文 → Director Product / Workflow / command API → 既有 Service / Persistence。

失败恢复时读取现有 Workflow → 使用最新 state_version 与 command_key → 调用既有 retry_analysis → 更新已有恢复引用。

任务、资产历史继续使用既有分页 API；本轮验证其真实 HTTP 返回，不重复开发历史接口。

Safe 前端 → 同源 /api 代理 → Safe API → 独立数据库；Safe Worker 使用相同数据库、artifact / runner 路径，保持 heartbeat。

## 测试

| 检查 | codex/testing | main |
| --- | --- | --- |
| 前端全量单测 | 63 文件 / 432 项通过 | 64 文件 / 428 项通过 |
| build / lint | 通过 | 通过 |
| Worker、Workflow、历史、启动脚本回归 | 61 项通过 | 初次 60 项通过、1 项旧断言失败；修正后相关 8 项通过 |
| 恢复合同、Provider 请求合同、claim fence 回归 | 68 项通过 / 5 项跳过 | 68 项通过 / 5 项跳过 |
| Director fixture 浏览器 | 1440 / 1024 / 768 / 390 四种尺寸通过 | 同样四种尺寸通过 |
| 真实前后端读取联调 | 7 页、60 次 API 返回 | 7 页、55 次 API 返回 |
| scoped Ruff / diff check | 通过 | 通过 |

Director fixture 注入一次 Workflow 创建失败、一次持久化分析失败，验证 Product 只创建一次、成功 Workflow 只创建一次，并调用 retry_analysis。fixture 不是实际 Provider 生成。

7 个真实联调页面为图片工作室、视频工作室、任务中心、生成资产、Provider 管理、个人设置、导演台。API 返回未经 mock；浏览器禁止写请求及对外请求，无页面异常。未配置 Kling 时主体列表返回 409 是明确的能力阻断，不记作生成成功。

5 项跳过均为需要 G1_TEST_POSTGRES_URL 的 PostgreSQL 参数化用例。本轮未提供该环境，不用 SQLite 冒充 PostgreSQL 验收。

## 环境

- 用户可用联调入口：http://127.0.0.1:5186/ → API 8013。
- main 源码隔离验证入口：http://127.0.0.1:5187/ → API 8014。
- 两个新隔离开发数据库通过既有 Alembic upgrade head，schema 为 ca01b2c3d406，health readiness 成功，Worker ONLINE。
- environment=test、directorWorkflowMode=offline_demo、openaiConfigured=false、paidGenerationEnabled=false、paidGenerationAuthorized=false、videoGeneration.available=false。
- 数据与证据位于 E:/Codex/validation/backend-frontend-connect-20261014；未复制真实 .env、密钥、运行数据库或生成产物到 main。
- readiness 的现有检查名称包含 postgresql，但本轮联调实际使用 SQLite；该响应不构成 PostgreSQL 验收证据。
- 正式版入口仍为 http://192.168.30.126:5173/。源码同步不是正式部署；本轮未切换正式前端代理、未迁移正式数据库、未重启正式服务。

## 发现与限制

- API 未配置不是前后端联调的前置阻塞，真实 Provider 生成保持禁止。
- 本轮验证了连接、读取、认证合同与失败恢复，不宣称真实 Product → Image → Video → Review → Delivery 已完成验收。
- Product 已创建但 Workflow 尚未成功时的复用限于同一页面；该窗口下刷新页面或响应结果未知的跨刷新幂等恢复仍需单独处理。
- 本轮没有重新启动或重新验收 PostgreSQL RC；中断恢复后的最后监听检查未见 8012 / 15439，不能沿用此前“RC 正在运行”的结论。
- 两个 worktree 均保留其他任务已有修改。Director、Worker 与新检查文件内容一致；api.ts、启动脚本和旧静态测试保留已核对的分支差异。

## 下一步

- 在零费用联调环境继续验收已有任务、审核与交付交互，不用生成占位产物替代真实结果。
- 正式上线前单独完成运行环境切换及数据库、认证、代理一致性验证。
- 用户配置 API 后，再验证真实分析和 Provider 只读能力；预算和生产授权确认后才能恢复单样本验收。
