# Sprint Report · Creative Workflow MVP-4B

日期：2026-10-12  
范围：在 MVP-4A `ProviderSubmissionTicket` 合同之上的持久化提交票据与单 worker 原子领取边界  
testing：`E:/Projects/libtv自动化生成`，`codex/testing`  
实际 main：`C:/Users/Reel/Documents/libtv-auto-main-sync`，`main`

## 完成

新增独立 `provider_submission_ticket` SQLAlchemy 模型和 Alembic
migration，持久化 MVP-4A 票据的完整 JSON 快照及可查询合同字段：

- request/evidence/preflight hash；
- owner、creative task、package revision、shot、provider、model；
- idempotency key；
- estimated cost、currency、quota units；
- manifest path、materialized input metadata、manifest hash；
- `READY_TO_SUBMIT`、`SUBMITTED`、`UNKNOWN`、`FAILED`、
  `INVALIDATED` 状态；
- Provider result JSON、result status、result summary、task ID、response
  digest 和 error 摘要。

`DurableSubmissionTicketStore` 使用数据库唯一幂等键和事务内
`INSERT ... ON CONFLICT DO NOTHING`。同键同快照返回原票据；同键不同票据
快照或 hash 返回 `IDEMPOTENCY_KEY_CONFLICT`。过期 READY 票据会持久化为
`INVALIDATED/TICKET_EXPIRED`；`UNKNOWN`、`FAILED` 和 `USER_STOPPED` 票据
不会重新变回可领取状态。MVP-4A admission 的过期、来源变化和授权撤回会
同步关闭已有 READY durable ticket。

本包没有执行 Provider POST、上传、quota reserve、charge、points ledger、
generation attempt 或旧 image/video 路径。图片仍使用 `image_edit`；
视频仍使用 `director_fixed`，仅保存提交边界合同。

## 修改

新增白名单文件：

- `backend/src/libtv_agent/creative/provider_submission_persistence.py`
- `backend/src/libtv_agent/services/creative_provider_submission_persistence.py`
- `backend/alembic/versions/e4f5a6b7c809_provider_submission_tickets.py`
- `backend/tests/test_creative_provider_submission_persistence.py`
- `docs/SPRINT_REPORT_CREATIVE_WORKFLOW_MVP4B_20261012.md`

未修改 `docs/ACTIVE_WORK.md`、`docs/CHANGELOG.md`、`domain/models.py`、
`domain/schemas.py`、API、OpenAPI、前端、旧 image/video service、Provider
adapter 或 `.env`。

## 测试

testing：

- MVP-4B 专项与 MVP-4A：`27 passed`；
- Creative 组合回归：`214 passed`；
- SQLite 覆盖跨 session durable replay、同键 hash 冲突、过期失效、
  `SUBMITTED/UNKNOWN/FAILED` 终态、停止失效和两个独立 session 的唯一
  claim 竞争；
- migration 结构测试确认新表、关键字段、幂等唯一约束和无 Provider/
  quota/ledger/attempt 外键；
- scoped Ruff：通过；
- 本包 `git diff --check`：通过。

专项负调用约束沿用 MVP-4A 的 Provider、上传、quota、points、ledger、
attempt 和旧 image/video 入口断言。本包 durable store 没有这些执行依赖。

实际 main 独立复验：

- 同一 MVP-4B/MVP-4A/Creative 组合：`214 passed`；
- MVP-4B 专项与 MVP-4A：`27 passed`；
- scoped Ruff、`git diff --check` 和 Alembic head 检查通过；
- testing/main 的 5 个白名单文件 SHA-256 一致。

## 发现问题

- 本包持久化 manifest 和临时 materialized input 路径及其 hash，但不复制
  素材字节；MVP-4A 的临时 lease 到期后，未来真实 Provider 接线仍需把输入
  重新物化到 durable object store，或在提交前建立新的 lease。
- SQLite 测试证明了本机单 worker/独立 session 的唯一 claim 结果；没有声称
  已证明 PostgreSQL 多 worker、跨进程锁等待、进程崩溃窗口、服务重启恢复
  或真实数据库带数据升级。
- 费用和额度字段只是提交前快照，仍没有 quota reserve、charge、ledger 或
  Provider 账单对账。

## 下一步与限制

本包只提供 durable admission record 和状态边界，不代表 Provider 已接线、
已生成、已成功、已人工 QUALIFIED 或可交付。后续真实提交包仍需在明确授权
下补 durable input lease、真实 Provider 调用、UNKNOWN 对账、费用原子化、
崩溃恢复和独立的 PostgreSQL 验证，并继续保持 `director_fixed` 与旧
automatic/custom image/video 行为隔离。

## 同步

testing 验证通过后，只将上述五个文件同步到实际 `main`，保留 main 的生产
专属差异、未提交改动、密钥、`.env`、缓存、运行时状态和构建产物。main 将
独立运行 MVP-4B 专项、MVP-4A/Creative 组合回归、scoped Ruff 和空白检查，
并记录两侧新增文件 SHA-256 一致性。上述同步和 main 独立复验均已成功；
没有执行生产迁移、部署、服务重启或真实 Provider 调用。

