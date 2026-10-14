# Sprint Report：Backend Final Acceptance Gap Closure

日期：2026-10-14
范围：stale worker claim fence、隔离 PostgreSQL 验收入口、Provider sandbox contract validation

## 完成

- 修复 stale worker 在对象存储物化期间被恢复后的执行边界：旧 claim 在下一次 launch fence 前可见，旧 Worker 返回 `None`，不产生成功语义。
- 回归测试确认 stale Worker 不调用 Provider，命令恢复为 `READY`，attempt 恢复为 `DISPATCH_PENDING`，reservation 保持 `RESERVED`。
- 新增只读最终验收脚本，串联 SQLite claim/race 回归、Provider sandbox 合同测试、隔离 PostgreSQL 目标校验、Alembic migration、readiness 和并发测试。
- PostgreSQL 目标限制为 `127.0.0.1:15439/g1_safety`，不读取或输出密码，不触碰生产数据库。

## 修改

- `backend/src/libtv_agent/runner/supervisor.py`
- `backend/tests/test_g1_claim_fence.py`
- `scripts/run-backend-final-acceptance.ps1`
- 本报告

未修改 Creative State、Workflow 架构、Provider adapter、UI 或生产配置。

## 测试

- SQLite claim/race 回归：`8 passed, 8 skipped`；跳过项为 PostgreSQL 参数化变体。
- Provider sandbox contract：`88 passed`，覆盖 request、preflight、durable ticket、executor、adapter boundary 和结果合同。
- Ruff：本轮修改 Python 文件通过。
- PostgreSQL：`BLOCKED`。当前未设置 `G1_TEST_POSTGRES_URL`，本机 5432 无监听，Docker Engine 不可用；因此 migration、readiness、PostgreSQL claim fence、worker concurrency 和 qualification revoke race 未执行。
- 付费 Provider：未执行。

## 发现问题

- PostgreSQL 证据仍是最终验收阻塞，SQLite 结果不能替代 PostgreSQL 行锁、跨进程 Worker 和事务隔离证明。
- 工作区已有媒体预算改动使部分旧的 `test_backend_readiness_repair.py` 场景缺少 exact model price；本轮 Provider sandbox 合同使用独立测试集通过，未修改该并行功能。

## 下一步

- 提供符合约束的隔离 PostgreSQL `G1_TEST_POSTGRES_URL`。
- 运行 `scripts/run-backend-final-acceptance.ps1`，取得 migration、readiness、claim fence、并发和 qualification revoke race 的 PostgreSQL 证据。
- 在 PostgreSQL 证据通过前，Backend 保持 `Conditionally Ready / Not Ready for final acceptance`。
