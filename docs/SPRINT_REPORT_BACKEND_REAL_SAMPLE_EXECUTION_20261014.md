# Backend Real Sample Execution Report

日期：2026-10-14，Asia/Shanghai。
前次失败网络复核：2026-10-14 17:42:07 +08:00 起。
执行结论：**BLOCKED，停止在 Product 创建前；真实样本闭环未执行，不标记 Passed。**

后续用户请求恢复 RC：17:54–17:55 复核恢复成功，详见 G 节；真实样本的商品、预算和生成配置前置条件仍未完成。A–F 节保留前次执行时的状态，不代表恢复后的在线状态。

## 完成与边界

- 本次授权范围按用户最新要求记录为单 Product、单 Image、单 Video；不继承旧准备文档的“只允许首帧”范围。
- 进行了 RC 文件身份核验、数据库只读预检和 HTTP 预检；登录调用可能产生正常 session / LOGIN 审计，不属于商品或生成操作。
- 没有修改业务代码、Workflow、状态机、Provider、数据库结构、运行配置或暂停状态。
- 没有创建真实 Product、Package、Image Request 或 Video Request；本次 Provider generation submit 为 0。
- 没有批量、追加生成、失败自动重投、人工资格判定或最终审批。
- API 和数据库连接失败后停止真实执行；未启动或重启服务，未迁移数据库，未切换 SQLite，也未转向正式环境。
- 本轮新增文件仅为本报告。报告同步不代表部署或生成授权扩大。

## A. 测试准备记录

| 项目 | 记录 | 当前判定 |
| --- | --- | --- |
| 目标 RC API | http://127.0.0.1:8012 | 当前连接拒绝 |
| 目标数据库 | PostgreSQL 127.0.0.1:15439/g1_safety | 当前连接拒绝 |
| 测试账户 | rc_acceptance；user_id f5158be4-b7d2-48b4-a8d8-50b461aae058；USER | 上次已验证；当前最终复核无法重新登录 |
| 真实商品来源 | 尚未提供本轮指定商品、SKU、商品正面原图路径/URL及其使用许可 | BLOCKED，不使用合成探针或擅选历史图片 |
| 预算上限 | 尚未提供本轮总金额及币种 | BLOCKED，不将默认每日额度或 pilot 次数当作本轮预算 |
| 价格目录 | 上次 RC 配置为 rc-unpriced-20261014，prices=[]，未知价格策略 reject | 配置文件哈希未变；本轮没有取得可归档的在线价格响应 |
| Image Provider | 既有 WaveSpeed 图片 adapter；商品参考图路径可映射 openai/gpt-image-2/edit | 精确请求参数、实际价格和在线能力待商品/运行环境恢复后核验 |
| Video Provider | kling_official_api，kling-3.0-omni，既有官方 API Executor | 上次 authentication / query Passed；本轮未提交、未重新验证外部查询 |
| Video 参数边界 | 上次能力为 3–15 秒、图片输入最多 7；本轮仅使用单生成图片 | 实际时长/音频/比例尚未冻结，不用能力上限充当请求预算 |
| fallback / 重试 | 上次 fallback disabled；本轮失败立即停止，不自动追加生成 | 保留既有恢复与对账语义，不改执行流程 |
| Director | 上次 live_director + aiAdapter=fake；分析路径为仓库确定性逻辑 | 不冒充真实 LLM 分析，也不使用 offline_demo 代替真实媒体 |
| 审核人 | 尚无本轮真人逐项审核结论 | 不能预填 QUALIFIED、APPROVED 或虚构审核时长 |

正式前端 http://192.168.30.126:5173/ 与本 RC 是不同环境；本轮不操作正式前端和 8000 维护 API。

### Pause 解除与恢复方式

冻结源码中现有接口为：

`POST /api/v1/admin/pause`

需要已登录 ADMIN、CSRF、最新 expectedVersion、reason 和以下字段：

`scope=GLOBAL|PAID_SUBMISSIONS`，`paused=false`。

两个 scope 分别更新；第一次成功后必须使用响应中的新版本调用第二次。结束或失败时通过相同接口分别恢复 `paused=true`，记录操作者、版本和审计事件。暂停只阻止后续提交，不能证明已提交的外部任务被取消或退款。

当前可用账户为 USER，不能承担 admin pause 操作；未使用角色覆盖、伪造 session 或直接 DML。尚未建立可用管理员会话。恢复服务后还需通过既有 runtime-config 接口核验/配置 pilot allow-list 和次数预算；pilotBudgetLimit 不是货币预算。

上次 RC 的 paidGenerationEnabled=false、dry-run、globalPaused=true、paidSubmissionsPaused=true；仅解除 DB pause 不等于开启真实生成。若后续需要运行配置调整，必须保持源码不变，重新登记 config manifest / revision，并受控验证启动，不能静默关闭价格拒绝策略。

## B. Runtime Identity 与实际预检

| 项目 | 本轮结果 |
| --- | --- |
| 冻结源码基础提交 | c6ef237af0a3a41a977a1fc4a5d821182d597864 |
| 源码指纹 | 10485925bc25a478d4dd6dae965b814095d99430240aa3b103deca8937eb81e3 |
| 源码文件身份 | 本轮重新计算，匹配 source-identity.json |
| 配置 manifest | .env、rc-secrets.json、kling-config.json、wavespeed-config.json 的哈希全部匹配；未输出秘密 |
| 上次数据库 head | ca01b2c3d406；本轮最终在线复核无法确认，不能沿用为当前 readiness |
| 上次 configRevision | e24e3d23fae71063ad3e0710ffea197dfe85576f210f93fca2153b8490c3b8fa；当前 API 无法读回 |
| /api/v1/health/ready | 最新请求 Connection refused，无 HTTP 状态码；不是 readiness=true |
| /api/v1/system/status | 最新请求 Connection refused，无 HTTP 状态码 |
| PostgreSQL | asyncpg 连接遭拒绝，未执行 migration 或数据库写入 |
| 监听及进程 | 最新查询未发现 8012/15439 监听；先前记录的 API 52104、worker 32252、PostgreSQL 31904 进程查询无结果 |
| 停止原因 | RC_RUNTIME_UNAVAILABLE；进程消失原因未查明，不猜测为业务代码缺陷 |

早先诊断脚本完成部分预检后，在只读审计查询中将 ISO 字符串绑定为 timestamptz，触发 asyncpg 类型错误。该诊断参数错误不属于 Backend 生产状态缺陷；未得到完整输出，不将其中未归档结果宣称 Passed。修正诊断参数后，数据库连接已遭拒绝，未进入下一生产阶段。随后仅复核网络和文件身份。

## C. 单样本逐步执行记录

| 阶段 | 本次 ID | 状态与 lineage | Provider handle | 审核事件 | 产物位置 |
| --- | --- | --- | --- | --- | --- |
| Product | 无 | NOT_EXECUTED；源商品未登记 | 不适用 | 无 | 无 |
| Package | 无 | NOT_EXECUTED；无真实 product/workflow/package/shot 关联 | 不适用 | 无 | 无 |
| Image Request / Output | 无 | NOT_EXECUTED；未上传本轮商品、未创建 batch/item/output | 无 | 无 | 无 |
| Qualification | 无 | NOT_EXECUTED；未产生图片，未写 QUALIFIED | 不适用 | 无 | 无 |
| Video Request / Attempt | 无 | NOT_EXECUTED；无 source_image_output_id 或 package binding | 无 | 无 | 无 |
| Review Required / Approved | 无 | NOT_EXECUTED；没有技术成功视频，不存在最终审批 | 不适用 | 无 | 无 |
| Delivery | 无 | NOT_EXECUTED；不声称 DELIVERABLE | 不适用 | 无 | 无 |

本轮无真实样本状态变化、Provider 回执、账单或产物。登录诊断可能新增 LOGIN 事件，但它不是图片资格事件或视频审批事件；当前数据库不可连接，未取得可归档的新审计 ID 或最终业务记录数量。

### 排除既有合成探针

RC 上次已存在的合成探针：

- Product：ea45b9e8-fb72-40ec-a5fc-5200c08bad08，SKU RC_RUNTIME_PROBE_20261014_SYNTHETIC。
- Workflow：d61683fd-273e-48fa-ae9d-7be1a8dd356e。
- Package：d61683fd-273e-48fa-ae9d-7be1a8dd356e:package:1。
- 使用 64×64 灰色合成图；上次状态 DRAFT → AWAITING_DIRECTION → PLAN_READY。

这些 ID 不属于本次真实商品，不能填入真实样本成功记录。上次 generation command、Provider submission ticket、AI usage reservation 均为 0；本轮最终数据库不可用，未宣称在线重新确认这些数量。

## D. 后续执行与数据关联合同

以下是恢复后必须通过的检查，不是本轮已通过的记录：

1. 冻结授权商品来源、源图 SHA-256、owner、SKU、许可、精确模型/参数/时长、两阶段报价和含所有调用的货币总上限。
2. 仅创建一个 Product 和一个 Workflow，保存 client_key、版本及包；分析失败时查询原 Workflow 并使用 retry_analysis，不重建 Product/Workflow。
3. 单 Image 请求保存 package_id、workflow_id、source lineage、shot/asset binding；保留原 Executor，提交前核对商品源图，记录 batch/item/output、Provider handle 和物化 hash/key。
4. 图片技术成功后停止等待真人检查，由现有 quality-decision API 写入真实 gates、QUALIFIED、审核人、时间、实际审核时长及事件。
5. 单 Video 请求绑定已合格 image output、同一 Package 与 storyboard/shot，保存 task/variant/attempt/command/claim 信息；资格撤销或源图/包不匹配即停止，不提交 Provider。
6. 技术成功与审批分开记录：SUCCEEDED 的待审投影 → REVIEW_REQUIRED → 真人 APPROVED → 满足已有物化/交付合同后的 DELIVERABLE。
7. 保留 review event、artifact/object key、下载验证及 hash、使用预占/结算或 UNKNOWN；失败不创建替代请求。已提交但未知只读查询/对账，不把未知当失败自动重投。

真实数据关联应能从最终 video artifact 反查：

`artifact → variant/attempt → task → source_image_output → image item/batch → package_id/workflow_id/shot → product/source hash/owner`

若现有选定 Package 要求超过本轮单 Image 上限，必须停止并记录范围冲突，不增加图片、不调整 Workflow 来绕过限制。

## E. 失败恢复能力与 Remaining Risk

- 本轮未创建真实业务实体，因此没有可恢复的真实样本，也未验证真实分析失败恢复。
- 上次 RC 有同 client_key 复用 Workflow 和 recovery 查询证据；它不能证明本轮真实 Provider 超时、断连、费用 UNKNOWN 的恢复。
- 上次冻结源码 PostgreSQL acceptance 为 26 Passed，本地 Provider sandbox 为 28 Passed；本轮未重跑，不等于真实 Provider 生成通过。
- Kling 上次只读 query 通过；官方独立 generation sandbox 未验证，不把本地 mock sandbox 当作官方 sandbox。
- 当前 RC 缺少进程存活与 readiness，无法验证 worker claim、Provider persistence、质量撤销 fence 和最终事务状态。
- 缺少本轮真实商品、货币预算、有效精确价格以及可用管理员操作上下文；不能使用默认配额代替授权或写假价格。
- Image/Video 真实成品质量、真人审核、成本结算、下载与交付均未验证。
- 上次 Workflow 列表 GET 返回 405，单项读取/恢复已通过；该历史 gap 未在本轮修复或重新验证。
- RC 是包含已有未提交改动的指纹化快照，不是不可变 Git release commit；报告不得替代发布签字。
- 无法确认进程消失的根因；不将该环境问题推定为已完成 Backend 修复的功能回归。

## F. 下一步与结论

1. 在单独的运行恢复窗口恢复原 RC API、worker 和同一 PostgreSQL，先复核身份、head、readiness 和原记录；本轮不自动重启。
2. 用户提供本轮指定商品正面原图/来源与 SKU/许可，以及总预算金额/币种；管理员准备精确价格、pilot 和可审计的暂停解除上下文。
3. 在上述前提完成后继续单样本，分别保留图片真人 QUALIFIED 和视频真人 APPROVED 检查点。
4. 每一步成功才进入下一步；任何失败停止追加提交，保存原 ID 与原因，按既有合同查询/对账。

**Passed：仅冻结源码和配置文件身份复核。**
**Blocked：当前 RC 不可用，真实样本执行停在 Product 前。**
**Remaining Risk：所有真实媒体、资格、Provider、审核、账务与交付行为仍未完成本次验收。**

本轮结论是执行环境 BLOCKED，不是声称 Backend 闭环缺失，也不是 Backend Real Sample Acceptance Passed。

## G. RC 恢复记录（后续请求，不改写前次执行结果）

2026-10-14 17:54:33–17:55:21 +08:00，用户明确请求“恢复RC”后完成恢复。

- 原 PostgreSQL 隔离集群使用同一 pgdata 启动，仍只监听 127.0.0.1:15439，数据库 g1_safety。
- PostgreSQL 日志显示此前非正常关闭；本次完成自动 WAL recovery 并进入 ready。此前进程消失的根因仍未确定。
- 未 initdb、未建替代库、未改数据库内容或结构、未执行 migration、未切换 SQLite。
- API 恢复在 http://127.0.0.1:8012；Worker 使用原 launch_rc.py worker 和原服务循环。
- API launcher / 实际进程 PID：22520 / 28420；Worker：6372 / 26784；PostgreSQL：47188。
- 源码指纹与配置 manifest 均匹配；sourceRevision、schemaRevision、configRevision 与 B 节原身份一致。
- /api/v1/health/ready：HTTP 200；postgresql=ok、databaseSchema=ok；无 maintenance header。
- Alembic 当前/预期 revision：ca01b2c3d406；missing tables=[]，schema readiness=true。
- Worker：ONLINE；同一实例两次心跳从 17:54:32.527 到 17:54:39.213，连续推进。
- rc_acceptance 登录/me：200；原 Workflow 单项读取及 client_key recovery：200，返回原 ID、PLAN_READY、state_version=2；此次成功诊断登录随后 logout=204。
- 诊断时曾误用不存在的 /creative-workflows 路由，失败后按冻结源码改为现有 /creative-workflow/tasks/{id} 和 /recovery/{client_key}；不是业务路由代码修复。
- Product=1、Workflow=1，仍是原合成探针；image batch、video task、generation command、attempt、submission ticket、AI usage reservation 均为 0。
- runtime control 版本仍为 1；globalPaused=true、paidSubmissionsPaused=true、internalPilotEnabled=false、pilotBudgetLimit=0。
- paidGenerationEnabled=false、paidGenerationAuthorized=false、executionMode=dry-run；未解除暂停，未发送生成请求。
- 在线价格目录确认 rc-unpriced-20261014、prices=[]；USER 访问 admin/runtime-config 返回 403，权限未提升。
- 仅恢复 RC；未操作正式环境、修改业务源码、Workflow、Provider 或运行配置。启动过程沿用既有只读 Provider readiness 检查，不属于媒体生成验收。
- 原有独立隐藏进程启动方式保留，未新增 Windows Service、开机自启或 watchdog；重启/异常退出后的长期存活保证仍不在本轮范围。

恢复证据保存在隔离 runtime 的 recovery-verification-20261014.json，processes.json 已更新实际 PID；这些运行时文件不推广到 main。

**RC Runtime 恢复：Passed。真实样本执行：仍 Blocked，尚缺商品来源、货币预算、有效价格和管理员生成窗口配置；未继续 Product → Delivery。**

本节仅为运行恢复记录。此前 C 节各生产阶段的 NOT_EXECUTED、无 Provider handle、无审核事件和无产物仍然成立。
