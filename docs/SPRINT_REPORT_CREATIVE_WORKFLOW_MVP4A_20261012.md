# Sprint Report · Creative Workflow MVP-4A

日期：2026-10-12
范围：在 MVP-3A 请求合同和 MVP-3B 只读预检之上的最小 Provider 提交边界
testing：`E:/Projects/libtv自动化生成`，`codex/testing`
实际 main：`C:/Users/Reel/Documents/libtv-auto-main-sync`，`main`

## 完成

新增纯服务层 `creative_provider_submission`，把当前有效的 MVP-3B
`READY_FOR_HUMAN_SUBMIT` 结果和独立人工 Provider 授权收口为不可变
`ProviderSubmissionTicket`：

```text
MVP-3B current preflight + ACTIVE human authorization/quote
→ manifest/path/hash recheck
→ READY_TO_SUBMIT immutable ticket
→ process-local idempotent claim
→ future adapter result: SUBMITTED / UNKNOWN / FAILED
```

票据绑定 owner、task、package、shot、request/evidence/preflight hash、
provider/model、稳定幂等 key、费用/币种/额度单位、临时素材 manifest、
过期时间和 image/video 分支。图片明确为 `image_edit` 和
`IMAGE_PROVIDER_ADAPTER_SUBMIT`；视频明确保留 `execution_mode=director_fixed`
和 `VIDEO_PROVIDER_ADAPTER_SUBMIT`。票据固定记录 `quota_reserved=false`、
`charge_recorded=false`、无 ledger/attempt ID，表示本包只允许形成提交凭证。

`admit_provider_submission` 要求调用方同时提供原预检和重新读取的当前预检，
比较除临时路径外的完整语义；它还重新检查 manifest 内容、素材存在性和字节
SHA-256、授权绑定、报价、预算和报价额度。任何过期、撤回、来源变化或状态
不一致都会拒绝，并使已存在的 READY 票据失效。

`SubmissionTicketStore.claim_submission` 使用进程内锁按幂等键登记。相同幂等键
和相同票据只返回原票据，不生成第二张票；相同幂等键对应不同哈希会返回
`IDEMPOTENCY_KEY_CONFLICT`。过期 READY 票据在再次领取时转为
`INVALIDATED/TICKET_EXPIRED`。

`ProviderSubmissionResult` 只定义未来 adapter 返回的最小对账合同：

- `SUBMITTED` 必须有 Provider task ID，后续不允许同票据再次提交；
- `UNKNOWN` 使用 `RECONCILE_ONLY`，不得自动重提；
- `FAILED` 使用 `EXPLICIT_NEW_IDEMPOTENCY_KEY`，同一幂等键不能重试。

## 修改

仅新增以下三个白名单文件：

- `backend/src/libtv_agent/services/creative_provider_submission.py`
- `backend/tests/test_creative_provider_submission.py`
- `docs/SPRINT_REPORT_CREATIVE_WORKFLOW_MVP4A_20261012.md`

没有修改 API、OpenAPI、数据库模型、migration、旧 image/video service、
provider adapter、前端或 `.env`。本包不创建 Provider task、image batch、
video task、attempt、quota reservation、points ledger 或账单记录。

## 测试

testing：

- 新增 MVP-4A 专项：`17 passed`。
- 组合回归：`303 passed`，其中 MVP-4A 新测试 17 项，MVP-3A/3B、
  preflight、image/video bridge、storyboard、media isolation、旧 fixed video
  和 image batch 回归 286 项。
- 组合隔离证据：`F:\Temp\creative-mvp4a-testing-final\junit.xml`。
- scoped Ruff：通过，覆盖新增服务、测试和 MVP-3A/3B/preflight/bridge 服务与测试。
- `git diff --check`：通过。

专项测试使用真实 MVP-3B fixture 和临时 SQLite/local object store。测试
monkeypatch Provider POST、上传、旧图片/视频提交、quota/points reserve、
settle 和 CreativeRecord `record` 入口为负调用；票据测试本身不接收 session，
因此没有任何数据库写入路径。覆盖 image/video 分支、不可变字段、manifest
哈希、过期/撤回/来源变化、重复领取、幂等冲突、SUBMITTED/UNKNOWN/FAILED、
UNKNOWN 不重提和失败同键不可重试。

## 发现问题

- `ProviderSubmissionTicket` 保存 MVP-3B 临时 materialization 路径，当前路径
  只在 preflight lease 存活期间有效；未来真实提交服务需要持久化或重新物化
  输入，不能把此内存票据直接当作跨进程 durable record。
- `SubmissionTicketStore` 仅使用当前进程的 `threading.Lock` 和内存字典。
  本包没有证明 PostgreSQL 唯一约束、数据库事务、多个 worker、进程崩溃窗口、
  服务重启恢复或跨实例同键竞争的原子性。
- 报价额度只被复制进票据并用于校验，没有执行 quota reserve、费用扣除、
  ledger 写入或 Provider 账单对账。

## 下一步与限制

本包不执行真实 Provider POST、不上传或验证 Provider 接收、不付费、不部署、
不执行迁移、不重启服务，也不证明真实像素质量或交付资格。

`READY_TO_SUBMIT` 只表示服务合同允许未来 adapter 边界接入；它不表示已经
生成、已经提交、已经成功、已经人工 QUALIFIED 或已经可交付。后续真实提交包
必须在数据库事务中实现 durable ticket、唯一幂等约束、预算/额度原子领取、
Provider 返回 UNKNOWN 对账、崩溃恢复和多 worker 竞争保护，并继续保留
`director_fixed` 与旧 image/video 行为隔离。

实际 main 独立复验：

- 同一 303 项组合回归通过，证据为
  `F:\Temp\creative-mvp4a-main-final\junit.xml`。
- main scoped Ruff 通过；testing/main 的本包三个文件 SHA-256 一致。
- 末尾空白修正后，两侧新增服务、测试和报告再次执行空白检查；未触碰
  main 其他工作树改动。

## 白名单与同步

testing 验证通过后，只同步上述三个 MVP-4A 文件到实际 `main`，保留 main
现有生产专属差异、未提交改动、密钥、`.env`、缓存、运行时状态和构建产物。
同步后在实际 main 独立运行同一新测试、组合回归、Ruff 和空白检查，并记录
两侧文件哈希一致。
