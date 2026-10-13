# CRB-2 实施包设计审查报告

日期：2026-10-12  
审查窗口：独立 CRB-2 设计审查  
当前 worktree：`E:\Codex\worktrees\0cda\libtv自动化生成`  
范围状态：仅设计，不开放真实 Provider 提交

## 审查结论

当前系统可以进入 CRB-2 的隔离实施设计，但不能直接开放 live。CRB-1
已经提供服务端只读 preflight；MVP-4B、MVP-5A、MVP-5B、MVP-7A 已提供
持久 submission ticket、durable input lease、图片 executor 和单样本编排
边界。编排器在 `LIVE_EXECUTION_DISABLED_MVP7A` 处仍然硬停止，旧图片入口
也没有 Creative package 到旧图片 batch/item/output 的持久绑定。

CRB-2 的最小实施目标应收敛为：

> 对一个已确认 owner、一个不可变 `FIRST_FRAME` package、一个已许可商品
> 版本、一个明确 Provider/model、一次初始 `image_edit` 请求，建立服务端
> 请求级授权 → durable ticket → durable input lease → 旧图片生产真源的
> 单次提交边界；提交结果不自动成为 `QUALIFIED` 或 `Deliverable`。

在下列合同没有由主 PM/用户确认前，CRB-2 只能继续运行隔离替身和
dry-run/replay，不能移除 live 硬闸：

- 具体 SKU、`ProductVersion` 和每个 Provider 输入的许可证据；
- 具体 Provider、model、能力声明和输入角色顺序；
- 报价、币种、单次及任务总预算、最大调用次数和授权有效期；
- 目标环境、管理员 live 开关和本次人工确认；
- 图片生产使用“每日图片额度”还是 points reservation/ledger，或经确认的
 统一账本方案；
- 提交后输出如何回收到 `ImageGenerationOutput`，以及真实像素检查和人工
 复核的入口。

## 审查基线

已读取 `AGENTS.md`、产品/设计/开发/QA/变更/技术审查基线、`ACTIVE_WORK.md`、
CRB Entry、CRB-1 以及 MVP-4B、MVP-5A、MVP-5B、MVP-7A、MVP-7B、迁移修复
报告。实际接口复核覆盖：

- `backend/src/libtv_agent/api/controlled_image_bridge.py`
- `backend/src/libtv_agent/services/controlled_image_bridge.py`
- `backend/src/libtv_agent/services/creative_provider_requests.py`
- `backend/src/libtv_agent/services/creative_provider_preflight.py`
- `backend/src/libtv_agent/services/creative_provider_submission.py`
- `backend/src/libtv_agent/services/creative_provider_submission_persistence.py`
- `backend/src/libtv_agent/services/creative_provider_input_lease.py`
- `backend/src/libtv_agent/services/creative_provider_executor.py`
- `backend/src/libtv_agent/services/creative_image_workflow_orchestrator.py`
- `backend/src/libtv_agent/api/image_generations.py`
- `backend/src/libtv_agent/services/image_generations.py`
- `backend/src/libtv_agent/services/image_quota.py`
- Creative/image domain models、points/ledger、WaveSpeed adapter 及相关测试。

## 最小目标与非目标

### 最小目标

1. 保留 CRB-1 的 preflight 入口和默认关闭策略。
2. 服务端从当前 `CreativeTask` 读取 package、锁项、Prompt、source/evidence
   hash 和 `state_version`；客户端只能提交 task/version，不得提交
   Provider、model、费用、权限布尔值或 object URL。
3. 重新验证 owner、package revision、ProductVersion、许可、人工授权、quote、
   capability、暂停/付费开关和当前执行状态。
4. 持久化或复用同一个 `idempotency_key` 的 ticket，创建或复用对应 durable
   input lease，并在外部副作用前完成单次 claim。
5. 将单样本请求转换为现有图片生产真源可接受的最小 batch/item 形态，或在
   无法无损转换时 fail closed；不得新增第二套 Provider 提交逻辑。
6. 通过现有图片轮询/输出物化链回收 `provider_task_id`、远端状态、输出 URL、
   object key、content type、字节大小和 SHA-256。
7. 将 Creative package、shot、candidate 与旧图片 batch/item/output 的映射
   保存为可恢复证据；人工审核、资格和交付继续使用各自的既有门。

### 明确非目标

- `director_fixed` 视频提交、`SHOT_01`、多镜和视频输出回收；
- 批量 Creative 生产、并行 worker 扩容或新 Agent 集群；
- 自动真实性循环、Critic、自动修订或额外调用；
- 修改旧 `generate` 命令语义或把 Fake/Replay 媒体升级为真实素材；
- 新的前端路由、前端 live 开关、客户端费用计算或客户端 Provider 选择；
- 重写 WaveSpeed 或其他 Provider adapter；
- 新建第二套 quota、points、billing 或 ledger；
- 生产迁移、部署、服务重启、真实付费验收或任何实际 Provider POST。

## 现有合同复用关系与缺口

| 现有边界 | 可直接复用 | 当前缺口 |
| --- | --- | --- |
| CRB-1 `POST .../preflight` | owner、版本、既有 request compiler 和 preflight validator | 响应固定 `provider_submission_allowed=false`，不能作为提交凭证 |
| `creative_provider_requests.py` | 不可变 package Prompt、角色顺序、request/evidence hash、稳定幂等键 | 当前图片请求只支持 dry-run/replay，且需要把真实执行写入旧图片真源 |
| `creative_provider_preflight.py` | capability、人工授权、quote、quota gate、许可、临时物化 | 仅做只读检查；quote/额度只是快照，不是原子预占 |
| `ProviderSubmissionTicket` / durable store | ticket 快照、唯一幂等键、`READY_TO_SUBMIT`/`SUBMITTED`/`UNKNOWN`/`FAILED`/`INVALIDATED` | 没有费用预占、旧 batch/attempt 关联、Provider 查询和输出回收 |
| `ProviderInputLease` | durable object copy、输入哈希、许可证据、过期/撤回、提交前重新物化 | lease 不跨 Provider 副作用提供完整恢复语义；孤儿 object 的清理策略未定 |
| `creative_provider_executor.py` | 图片上传、POST、响应摘要和 `UNKNOWN` 分类 | 不创建 `ImageGenerationBatch/Item/Output`、`ImageQuotaReservation`、attempt 或 ledger |
| `creative_image_workflow_orchestrator.py` | ticket → lease → executor 审计结构和 stop/UNKNOWN/FAILED 边界 | live 明确在 `LIVE_EXECUTION_DISABLED_MVP7A` 停止 |
| 旧 `/image-generation-batches` | 旧 batch/item、WaveSpeed upload/submit、图片 quota、poll、输出物化和下载 | 只接受 multipart 客户端上传；Creative package/source mapping 没有正式字段或外键 |
| 旧图片 `refresh_batch` | provider task 查询、输出下载、校验、object store 写入 | 只轮询 `CREATED/PROCESSING` 且要求已有 provider task id；没有 Creative UNKNOWN reconcile 入口 |
| `PointsReservation/PointsLedger` | 既有任务型费用预占、consume/release/uncertain 语义 | 旧图片路径不使用 points ledger，直接接入会改变计费边界，必须确认 |

重点缺口是两个执行真源目前没有闭合。Creative executor 能够得到
`SUBMITTED`，但结果只写回 durable ticket；旧图片链能够写回
`ImageGenerationItem` 和 `ImageGenerationOutput`，但不认识 Creative
package/candidate。两者不能通过删除 live 硬闸自动连接。

旧图片链还有一个必须保留的语义：`submit_batch` 在 Provider POST 前将 item
置为 `SUBMITTING`，若提交结果无法确定则写 `WRITE_UNCERTAIN`；旧轮询只处理
有 `provider_task_id` 的活动 item。因此 CRB-2 必须把“无 task id 的未知提交”
进入人工/服务端 reconcile 队列，禁止重新走同一幂等键。

## CRB-2 建议状态边界

### 请求级授权

请求入口只接收 `task_id`、`expected_version` 和服务端生成或服务端保存的
command/idempotency key。服务端重新读取并固定：

```text
owner
CreativeTask.state_version
package_id + package revision
locks_hash + preservation_hash
ProductVersion + source hash
shot_id = FIRST_FRAME
provider + model
request_hash + evidence_hash
quote_id + cost + currency + quota_units
license ids + license expiry
authorization expiry + max_calls + max_cost
administrator live switch
human confirmation
```

任何 package、锁项、来源、许可、Provider/model、quote、预算、有效期或执行
状态变化都使旧 preflight/ticket/lease 失效。前端 readiness、旧
`paid_submission_consent_at` 或 `provider_submission_allowed` 布尔值不能
替代这些证据。

### Package/version

`package_revision_id` 必须绑定不可变 package，而不是仅保存一个可重新解释的
字符串。提交前应比较当前 task snapshot、package contract、text contract、
facts revision、source hash 和 request/evidence hash。新 revision 产生新的
幂等键和新的授权；旧 revision 不可原地更新、不可追认新素材。

### Ticket/claim

推荐保留现有 ticket 状态，并明确状态含义：

```text
READY_TO_SUBMIT
  → SUBMITTED       已取得 provider_task_id，等待旧图片轮询/回收
  → UNKNOWN         外部副作用或结果不可确定，只能查询/对账
  → FAILED          确认未提交或提交失败；重试必须新幂等键
  → INVALIDATED     过期、撤回、停止、来源变化或合同冲突
```

durable claim 必须发生在 Provider upload/POST 前，并且同一 ticket 在两个
session/worker 中只有一个获胜者。现有 SQLite `INSERT ... ON CONFLICT` 测试
证明了本机唯一 claim；PostgreSQL 多 worker、进程崩溃和锁等待仍需单独证明。

### 素材 lease

提交前按以下边界执行：

```text
ACTIVE
  → MATERIALIZED
  → Provider upload/POST
  → 保留 durable object 和 manifest 作为恢复真源
```

每个输入继续绑定 role、order、adapter field、原始 object key、durable object
key、SHA-256、媒体类型、大小和 license evidence。撤回、过期、字节变化、
对象缺失、package/source 变化必须阻断提交并撤回 lease。临时路径只服务一次
adapter 调用；不得把临时路径或浏览器 File 放进 CreativeTask 真源。

### 费用、额度与账本

当前 ticket 仅保存 `estimated_cost_micros`、`currency` 和 `quota_units`。
它们是授权快照，不是预占，也没有防止跨 worker 超额的原子账户更新。

CRB-2 必须先冻结以下一种方案，这属于“需主 PM/用户确认”：

1. 图片继续使用 `ImageQuotaReservation` 作为唯一额度真源，并新增经批准的
   provider cost/ledger 记录；
2. 图片统一接入现有 `PointsReservation/PointsLedger`，明确图片单位、币种、
   估算点数、实际费用和 UNKNOWN 结算；
3. 另有已批准的 billing service/ledger，并提供幂等键和对账合同。

无论选择哪一种，都必须满足：

- 预占只发生一次，并与 durable batch/attempt 绑定；
- 预占成功后才允许 Provider upload/POST；
- 预提交失败可释放，已提交但费用未知必须进入 `UNKNOWN/UNCERTAIN`；
- Provider 回执或人工对账后只产生一次 consume/release/uncertain 事件；
- 同键重放不重复扣费，旧 ticket 不能借新 quote 继续执行；
- 费用、额度和 ledger 的最终状态不能由 Creative 前端推断。

在上述方案确定前，CRB-2 不应实现任何真实扣费或额度写入。

### 结果回收

真实提交回执至少需要：

```text
ticket_id
idempotency_key
provider
model
provider_task_id
provider status/raw status
response digest
actual submitted verdict
quote/charge evidence
```

取得 `provider_task_id` 后，结果由既有图片轮询和物化链处理：状态查询、远端
输出 URL、下载、媒体类型/尺寸/字节 SHA-256、object store key 和
`ImageGenerationOutput`。Creative mapping 只能在旧输出记录完整且哈希一致后
写入。技术完成不等于人工 `QUALIFIED`，人工质量接口也不等于交付。

### UNKNOWN 恢复

- 有 `provider_task_id`：只做 provider GET/查询，成功后绑定旧 item，失败或
  终态按既有状态机结算。
- 没有 `provider_task_id`：保留 `UNKNOWN/WRITE_UNCERTAIN`，不得自动 POST；
  通过服务端 reconcile 使用 provider 支持的请求查询、账单/后台证据或人工
  确认决定“未提交、已提交、无法判定”。
- 已确认已提交：绑定远端 task 后继续轮询，保留原 ticket 和费用证据。
- 已确认未提交：只能用新 package/version 或新幂等键重新授权；旧票据不复活。
- 无法判定：持续阻塞生产资格和额度释放，直到人工/服务端对账完成。

现有 Creative ticket 状态没有 `RECONCILED` 或明确的 provider query
evidence 字段；若要把 UNKNOWN 结果正式接入旧图片恢复，新增状态/字段/API
属于“需主 PM/用户确认”，不能在 CRB-2 自行扩大。

## 实施包文件边界

### 本次实际修改白名单

本审查窗口只新增本文件：

```text
docs/CRB2_IMPLEMENTATION_PACKAGE_REVIEW_20261012.md
```

没有修改 backend、frontend、OpenAPI、迁移、生产配置、scripts、既有 Sprint
Report、`.env`、运行时状态或 Provider adapter。

### 后续 CRB-2 实施白名单建议

只有主 PM 接受本报告并冻结合同后，实施窗口才可在以下范围内建立独立变更：

```text
backend/src/libtv_agent/api/controlled_image_bridge.py
backend/src/libtv_agent/services/controlled_image_bridge.py
backend/src/libtv_agent/services/creative_image_workflow_orchestrator.py
backend/src/libtv_agent/services/creative_provider_executor.py
backend/src/libtv_agent/services/creative_provider_input_lease.py
backend/src/libtv_agent/services/creative_provider_submission_persistence.py
backend/tests/test_controlled_image_bridge.py
backend/tests/test_creative_image_workflow_orchestrator.py
backend/tests/test_creative_provider_executor.py
backend/tests/test_creative_provider_input_lease.py
backend/tests/test_creative_provider_submission_persistence.py
backend/tests/test_crb2_controlled_image_submission.py
docs/contracts/controlled-image-bridge-submit.v1.md
```

以下文件如果需要变更，必须先标记为“需主 PM/用户确认”并重新划分实施包：

```text
backend/src/libtv_agent/api/image_generations.py
backend/src/libtv_agent/services/image_generations.py
backend/src/libtv_agent/services/image_quota.py
backend/src/libtv_agent/domain/models.py
backend/src/libtv_agent/domain/schemas.py
backend/src/libtv_agent/domain/enums.py
backend/src/libtv_agent/services/points.py
backend/src/libtv_agent/runner/supervisor.py
backend/src/libtv_agent/adapters/wavespeed.py
backend/src/libtv_agent/config.py
backend/src/libtv_agent/app.py
openapi.yaml
backend/alembic/versions/*
.env*
```

在确认前禁止修改：

```text
frontend/*
scripts/*
docs/ACTIVE_WORK.md
docs/CHANGELOG.md
docs/SPRINT_REPORT_*.md
既有迁移文件
生产运行目录、密钥、缓存、构建产物和真实运行时状态
```

## 隔离替身测试矩阵

| 类别 | 必须证明 |
| --- | --- |
| 请求准入 | owner 越权、过期 version、package 变化、锁项/hash 变化、撤回来源、未批准 ProductVersion、许可缺失/过期、Provider/model 不匹配均拒绝 |
| 授权 | 人工确认缺失、管理员 live 开关关闭、环境不符、暂停开关、quote 过期、币种不符、单次/总预算超限、调用次数超限均拒绝 |
| Ticket | 同键同快照返回同一 ticket；同键不同 hash 冲突；两个 session/worker 只有一个 claim；过期、停止、UNKNOWN、FAILED 不可沿原键执行 |
| Lease | durable copy、跨 session replay、owner 隔离、对象缺失、字节篡改、媒体类型变化、许可变化、过期/撤回、提交前二次校验 |
| Provider 边界 | dry-run/replay 零 upload/POST；test-double 必须显式注入；live 替身每个 ticket 最多一次 upload/POST；不能把返回结果写成 QUALIFIED |
| 旧图片接线 | 单 item batch 幂等创建；旧 batch/item/provider task/output 映射完整；不重复上传/提交；旧图片接口和历史任务行为回归通过 |
| 费用/额度 | 预占一次、拒绝不扣、同键不重复扣、失败释放、UNKNOWN 保留不确定、已确认提交只结算一次；对账后 ledger 事件幂等 |
| 结果回收 | provider task 查询、远端失败、输出 URL 缺失、下载失败、对象写入失败、哈希不匹配、部分输出均保持可恢复且不误报成功 |
| UNKNOWN | 有 task id 只查询；无 task id 不自动重投；进程重启后票据/lease/batch 恢复；人工 reconcile 后只能进入明确终态 |
| stop/revoke | 用户停止、授权撤回、来源撤回、package 失效在提交前阻断；已提交任务继续查询/结算，不被伪装成取消未发生 |
| 兼容性 | 旧 image generation batch、quota、download、quality decision、任务刷新和历史 URL 深链接的原有测试不回归 |

## 验收门槛

CRB-2 设计包只有同时满足以下条件，才可申请进入后续真实验证：

1. 主 PM/用户书面接受本报告的单样本范围、文件白名单和非目标。
2. 完成具体 SKU、ProductVersion、素材许可、Provider/model、quote、预算、
   币种、最大调用次数、有效期、目标环境、管理员开关和人工确认。
3. `codex/testing` 中隔离替身矩阵全部通过，包含双 session/多 worker 竞争、
   进程重启、输出写失败和 UNKNOWN 恢复。
4. 费用/额度/账本方案被确认，并由真实数据结构或既有服务证明幂等预占和结算。
5. PostgreSQL 独立验证完成；SQLite 通过不能替代多 worker、锁、崩溃窗口或
   带数据升级证明。
6. 旧图片链 scoped 回归、Creative scoped 回归、Ruff、必要的 backend tests
   和 `git diff --check` 通过。
7. testing 与实际 `main` 分别复验；只同步本包白名单，不同步 secrets、迁移
   执行结果、运行时状态、构建产物或未授权配置。
8. 真实 Provider 单样本另立 CRB-5 授权记录；CRB-2 通过不等于
   `PRODUCTION_LOOP_READY` 或 `PRODUCTION_READY`。

## 必须等待人工提供的信息

以下信息缺一项，实施窗口只能继续替身测试：

| 决策项 | 必须具体到 |
| --- | --- |
| SKU/素材 | `Product.id`、`ProductVersion.id`、正面原图 object key/hash、每个输入许可 ID/evidence/expiry |
| Provider/model | Provider 名称、model id、能力快照、输入上限、输出格式/分辨率和远端查询方式 |
| 预算 | 单次成本、币种、quote id、单次上限、任务总上限、最大 POST 次数、有效期 |
| 运行环境 | staging 或 production、配置版本、Provider credentials 已验证、目标服务实例 |
| live 开关 | 管理员开关位置、开启范围、回滚方式、暂停开关和审计人 |
| 人工确认 | 对这个精确 task/package/provider/model/hash 的一次确认，不接受泛化“阶段已批准” |
| 账本政策 | 图片使用 image quota、points ledger 或其他已批准真源；UNKNOWN 如何计费/释放 |
| 输出政策 | provider 输出如何物化、像素检查谁负责、何时允许人工 QUALIFIED、交付如何单独批准 |

## testing → main 同步策略

1. 以后续实施窗口在 `codex/testing` 建立独立提交，只包含白名单文件。
2. 先在 testing 运行替身矩阵、旧图片回归、Creative 回归和数据库/多 worker
   证据；不启动服务、不执行迁移、不调用 Provider。
3. 按文件指纹把同一局部变更同步到实际 `main`，逐文件比较并保留 main
   的生产专属差异；禁止整树覆盖或携带 `.env`、缓存、运行时状态和生成物。
4. 在实际 main 独立重跑同一组检查并记录 hash/差异；同步成功仍不表示部署、
   服务重启、生产迁移或真实付费授权。
5. 只有主 PM/用户完成 CRB-5 请求级确认后，另行执行单样本 live 验证；UNKNOWN
   先对账，不能自动重投。

## 本次交付

- 报告路径：`docs/CRB2_IMPLEMENTATION_PACKAGE_REVIEW_20261012.md`
- 审查结论：CRB-2 可进入隔离实施设计，当前不能开放真实 Provider。
- 阻塞项：具体 SKU/许可、Provider/model、报价/预算/额度账本、环境、管理员
  live 开关、人工请求确认、输出回收和 UNKNOWN reconcile 合同。
- 未修改范围：backend/frontend/OpenAPI/数据库迁移/生产配置/Provider、
  scripts、既有 Sprint Report、`.env`、运行时数据、服务进程和真实数据。
- 可执行下一步：主 PM 先确认本报告的单样本范围、账本方案和条件清单；确认后
  由独立实施窗口按白名单完成 CRB-2 替身接线与 testing 验收，再按同一白名单
  局部同步 main。

