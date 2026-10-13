# CRB-2 隔离替身 Sprint Report

日期：2026-10-13

## 完成

- 在独立 worktree 中复用现有 fake/replay Creative `FIRST_FRAME` 路径。
- 为 synthetic batch/item/output 增加可追踪的 package revision、ProductVersion、source hash 和离线资格元数据。
- 保持 `provider=fake`、`fake://`、`OFFLINE_SYNTHETIC_ONLY`、输出 `PENDING/qualified=false` 和 `deliverableEligible=false`。
- 保持同一 command/idempotency key 重放返回原结果，不重复创建 batch、额度预占或 points ledger。
- 新增源图哈希变化、package 变化、ProductVersion 变化的 fail-closed 验证。

## 修改

- `backend/src/libtv_agent/services/creative_workflow.py`
- `backend/tests/test_crb2_isolated_replay.py`
- `docs/SPRINT_REPORT_CRB2_ISOLATED_20261013.md`

## 测试

- scoped pytest：39 passed，覆盖 CRB-2 专项、Creative workflow、recovery、media isolation 和 submission recovery。
- scoped Ruff：通过。
- `git diff --check`：通过；Git 仅提示既有 `submission_recovery.py` 的 LF/CRLF 转换，不是空白错误。
- 未启动服务，未执行真实 Provider、上传、迁移、生产写入或账本操作。

## 发现问题

- 未开放真实 Provider、上传、生产账本、迁移、配置或服务流程。
- PostgreSQL 多 worker、进程崩溃和 UNKNOWN reconcile 仍属于后续人工确认边界；本 Sprint 只证明 SQLite 离线替身语义。
- 扩展回归曾尝试收集 Creative 全套测试，但 `test_creative_offline_readiness.py` 依赖白名单外的 `scripts/check_creative_offline_readiness.py`，因此按边界未复制或修改 `scripts`，扩展回归已停止。

## 下一步

- 由主 PM 审查 testing worktree 的白名单 diff。
- 在账本、请求级授权和 UNKNOWN 对账合同明确前，不进入真实 Provider 验证。
