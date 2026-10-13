# CRB-2 恢复与停止验收 Sprint Report

日期：2026-10-13

## 完成

- 复核 Creative workflow 现有离线恢复合同。
- 确认 `UNKNOWN` 和 `WRITE_UNCERTAIN` 会保留未知执行证据，并阻断新的
  `generate`、`revise` 和 `authorize`。
- 确认只有显式 `reconcile_not_submitted` 才能恢复离线流程；未知结果不会
  自动重投。
- 确认 `stop`、素材撤回和未知执行后的阻断状态会保留 append-only 审计记录。
- 确认应用重建后可以从持久化 snapshot 恢复未知状态。
- 确认本地 submission recovery 的 `retryAllowed` 永远为 `false`，未知或
  找不到的结果要求进一步处理。

## 修改

- 仅新增本报告。
- 未修改 backend、frontend、ORM、迁移、quota、points/ledger、Provider、
  config、OpenAPI 或生产运行状态。

## 测试

testing 与实际 `main` 分别运行并通过 33 项：

```text
backend/tests/test_creative_workflow.py                         21
backend/tests/test_creative_workflow_recovery_contract.py         5
backend/tests/test_creative_workflow_stop_audit.py                2
backend/tests/test_submission_recovery.py                         5
```

覆盖内容包括：

- `UNKNOWN` / `WRITE_UNCERTAIN` 阻断与显式 reconcile；
- 未知执行后的成本和调用次数恢复；
- stop 后新执行拒绝与审计保留；
- 素材撤回后的新执行拒绝；
- 应用重建后的未知状态恢复；
- submission recovery 查询与禁止自动重试。

## 发现问题

- 独立专项窗口尝试新增 CRB-2 recovery test 时，fork worktree 的 app/router
  没有接入当前 testing 工作树中的 Creative products/API 入口，测试请求返回
  `404`。该问题属于独立 worktree 快照不完整，不是当前 testing/main 回归中
  已证明的业务失败。
- 为避免扩大本 Sprint 白名单，没有修改 router、API 接入或数据模型；使用现有
  33 项回归作为验收证据。
- PostgreSQL 多 worker、进程崩溃窗口、真实 Provider 对账和真实账本结算仍未
  验证。

## 下一步

- 保持真实 Provider 和真实样本冻结到 CRB-5。
- 在请求级授权、Provider/model、预算、账本真源和 UNKNOWN 对账合同明确后，
  再设计最终单样本验证。
- 不因本 Sprint 通过而宣称 `PRODUCTION_LOOP_READY` 或 `PRODUCTION_READY`。
