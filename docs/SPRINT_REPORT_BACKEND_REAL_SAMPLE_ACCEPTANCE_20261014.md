# Backend Real Sample Acceptance Report

日期：2026-10-14，Asia/Shanghai。
检查时间：16:48–16:52。
结论：**BLOCKED，真实商品生产闭环尚未执行，不能判定 Passed。**

## 完成范围

- 只读核验当前监听 API、正式入口的 API 代理、隔离 PostgreSQL、运行配置与现有审核合同。
- 未修改代码、配置、数据库结构或状态机。
- 未运行 migration、启动新应用、切换维护模式或重启服务。
- 未创建 Product、Workflow、Image/Video Request，也未提交 Provider、消耗生成费用或执行批量生产。
- 本轮新增文件仅为本报告，并同步至 main。

## Passed：已通过的检查

| 检查 | 实际证据 | 结论 |
| --- | --- | --- |
| 当前 API 存活 | `GET /api/v1/health/live` 返回 HTTP 200、`status=ok` | Passed，仅证明服务存活 |
| 维护边界 | Product、Director 查询入口均返回 HTTP 503、`MAINTENANCE_QUERY_ONLY` | Passed，边界生效；同时阻止本轮执行 |
| 隔离 PostgreSQL schema | `127.0.0.1:15439/g1_safety`，实际/预期 revision 均为 `ca01b2c3d406`，missing tables 为空 | Passed，只读检查 |
| 隔离环境清理状态 | 没有遗留 `acceptance_*` 或 `test_*` schema | Passed |

隔离数据库的 Product、CreativeTask、ImageGenerationBatch、ParentTask、User 均为 0 条。它不是已经运行真实样本的 Backend，也没有可复用的样本关联链。本轮通过 READ ONLY 事务查询，未建表或写入记录。

## Blocked：当前运行环境

本地监听 API：`http://127.0.0.1:8000`。
正式入口：`http://192.168.30.126:5173/`，其 `/api` 请求代理到 Backend。

1. **运行数据库落后于验收版本。**
   - 实际健康路由 `GET /api/v1/health/ready` 返回 HTTP 503。
   - `databaseSchema=outdated`。
   - current revision：`c8e9f0a1b2c3`。
   - expected revision：`ca01b2c3d406`。
   - missing tables 为空不代表 migration 已完成。
   - 正式入口代理的同一路由也返回上述 503。
   - 本轮禁止修改数据库结构，因此没有尝试升级。

2. **当前 API 是维护查询入口。**
   - 健康和系统状态响应带 `X-LibTV-Maintenance: query-only`。
   - `GET /api/v1/products`、`GET /api/v1/creative-workflow/tasks` 返回 `MAINTENANCE_QUERY_ONLY`。
   - 现有 `maintenance.py` 生命周期只建立数据库连接，不启动正常 Worker/recovery/provider probes；其 HTTP 边界只允许指定的查询和登录/登出。
   - 没有绕过该入口改调内部 Service，也没有另起进程连接现有运行数据库。

3. **Director 当前运行模式不满足真实链路要求。**
   - 实际 `/api/v1/system/status`：`environment=development`、`aiAdapter=openai`、`directorWorkflowMode=offline_demo`。
   - 当前代码中的 `director_response_mode` 只允许 test + fake/replay 使用 offline_demo；否则拒绝 `OFFLINE_WORKFLOW_DISABLED`。
   - 这是基于运行配置与现有代码发现的后续阻塞，尚未通过写请求验证；当前维护边界先行阻断。

4. **视频 Provider 合同尚未在该运行环境通过可用性验证。**
   - provider：`kling_official_api`；model：`kling-3.0-omni`。
   - status：`KLING_API_CONFIGURED_UNVERIFIED`。
   - `available=false`、`authenticated=false`。
   - 返回原因：已配置凭据，但未通过官方只读 task-query 验证。
   - 这不等于已证明凭据无效；维护入口不会执行正常启动 probes。
   - 虽然运行配置报告 `paidGenerationEnabled=true`、`paidGenerationAuthorized=true`，它们不能替代 schema、维护边界、Director 或 Provider readiness。

5. **样本与账户尚未指定。**
   - 本轮没有提供商品 Product ID、原图路径或商品源，以及对应测试账户。
   - `GET /api/v1/auth/me` 在当前请求上下文返回 401；运行环境启用 shared authentication。
   - 未读取已有 session token、借用其他账户或伪造 `X-User-Id`。
   - 工作区存在多个账户的历史素材，不能仅凭文件存在认定它就是本次样本、已授权源或该账户的合格产物。

## A. 每一步状态变化

本次没有发生生产状态变化。以下“待验证内容”不是实际执行结果：

| 步骤 | 本次状态 | 待验证内容 |
| --- | --- | --- |
| 输入真实 Product | Blocked / 未执行 | 源文件、owner、Product/Version、产品确认与 license VERIFIED |
| 创建 Director Package | Blocked / 未执行 | 创建/分析/选向、冻结 package、workflow 与 source binding |
| 生成 Image Request | Blocked / 未执行 | 请求和输出保留 package lineage；实际生成与持久化 |
| 图片资格确认 | Blocked / 未执行 | 真实图片审查后 PENDING → QUALIFIED，审查人和依据可追踪 |
| 创建 Video Request | Blocked / 未执行 | source image、package binding、shot/order、request contract |
| Worker 与 Provider 执行 | Blocked / 未执行 | claim ownership、提交前资格检查、Provider handle、结果持久化 |
| Review Required | Blocked / 未执行 | 技术成功、下载完成且技术校验通过，进入待审队列 |
| Approved | Blocked / 未执行 | 产品保真、编辑组装与 HUMAN_CRITICAL 人工审核通过 |
| Deliverable | Blocked / 未执行 | 审批后正确聚合为 DELIVERABLE，交付文件可读取 |

现有状态合同：用户所称 Review Required 对应 parent `AWAITING_FINAL_APPROVAL` 和待审批的 variant；审核写入 variant `final_approval_status=APPROVED` 后，parent 聚合为 `DELIVERABLE`。本轮没有人为新增“Review Required”状态，也没有伪造审核耗时或通过结果。

## B. 数据关联链

本次没有创建下列 ID，因而不存在可报告的真实样本链：

`user → Product/Version → Workflow → Package/shot → Image batch/item/output → staged upload/source image → Video task/variant/attempt/command → Approval → DownloadArtifact/Delivery`

待实际验收时必须从持久化记录核对：

- Product 与 Workflow 的 owner 相同。
- Package 的 workflowId、packageId、shotId、产品版本、sourceHash 和 packageHash 相互对应。
- Image Request 的 frozen prompt/source 与 Package 绑定一致；产物有真实 Provider handle、object key、sha256。
- Video Request 的 sourceLineage 指向该合格 Image Output，并保留相同 Package/shot 和 storyboard order。
- Worker claim、Provider submit/result 与同一 attempt 对应。
- 审核事件、审查人、技术校验和交付文件指向该 variant/task。

这些字段的现有代码实现不等于本次真实数据验证通过。

## C. 失败恢复能力

本次没有执行故障注入、分析失败重试、请求重放或 Worker 恢复。因此：

- 不声称已证明同一个真实 Product/Workflow 的分析失败恢复。
- 不声称已证明真实 Provider 超时、未知提交结果或计费不确定时不会重复生成。
- 不声称已证明该样本的资格撤销、断线恢复与交付恢复。

先前 PostgreSQL 验收报告中的两侧 26 项通过包含模拟 Provider、合成媒体和隔离数据库恢复测试。这些是历史合同证据，不能替代本轮真实商品验收，也不能证明当前维护 API 已部署该验收候选版本。

## D. 发现的问题与 Remaining Risk

- 隔离 PostgreSQL Ready 与当前运行 Backend Ready 是两个不同结论；当前运行数据库尚未到验收 head。
- 正式入口 `/health/ready` 返回 HTTP 200 的 HTML，是前端路由回退，不是 Backend readiness 成功。正确的代理检查为 `/api/v1/health/ready`。
- `/api/v1/system/status` 报告运行 sourceRevision：
  `772314bf22372850b2bc80158345144da0ef8eddead9a2d586787dc161d0ff7a`。
  只读检查时 testing/main 的源码指纹与之不同，且两侧仍有并行未提交改动；尚未建立该运行服务与不可变 Release Candidate 的对应关系。
- 实际运行配置应以 API status 为证据。当前工作目录 `.env` 的配置不等同于运行进程配置；本轮未根据其空凭据字段宣称运行 Provider 未配置。
- 真实图片保真、人物缺陷、视频解码、供应商稳定性、真实计费、对象存储及交付读取仍未验证。
- 审核接口要求 HUMAN_REQUIRED hard gates。真实样本必须保留实际人工审核记录，不能用技术成功或模拟审批代替。

## 下一步与同步

继续执行需要一个已部署且 schema readiness 通过、开放正常生成链路的 RC API；指定真实商品样本和其测试账户，并具备可验证的 Provider 与预算边界。执行前应记录候选源码/配置身份；每阶段保留请求、状态、关联 ID 和审核依据。

迁移、配置切换或服务部署属于当前限制之外，本轮没有执行。

本报告同步至实际 main：`C:/Users/Reel/Documents/libtv-auto-main-sync/docs/SPRINT_REPORT_BACKEND_REAL_SAMPLE_ACCEPTANCE_20261014.md`。只同步报告；没有同步配置、账户数据、凭据、素材或 runtime artifacts。

最终分类：**Passed：只读前置检查；Blocked：真实样本闭环；Remaining Risk：全部尚未取得真实生成、恢复、人工审核与交付证据的环节。**
