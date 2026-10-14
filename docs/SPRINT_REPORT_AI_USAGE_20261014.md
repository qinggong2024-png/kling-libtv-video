# Sprint Report：AI 风险额度最小闭环

日期：2026-10-14
范围：分析和 Prompt Assistant 的持久化风险额度保护；Feedback Learning 延期。

## 完成

- 为 AI 分析和 Prompt Assistant 增加独立 `AIUsageReservation`、
  `AIUsageQuotaSummary` 与 append-only `AIUsageLedger`。
- 在 Provider 调用前以短事务预占风险单位，Provider 期间不持有数据库锁。
- 成功结算，明确本地未提交释放，timeout/异常无法确认提交时保留 `UNKNOWN`。
- 分析 fallback 使用独立幂等键和额外预占；Prompt Assistant 的 `ADVISE`、
  `REGENERATE` 均通过额度门。
- Prompt Assistant 增加 `Idempotency-Key`，前端同步发送；同用户、任务、操作和 key
  的重放不重复预占或 Provider 调用。
- Fake/Replay 标记为离线结算，不报告真实费用。

## 修改

- `backend/src/libtv_agent/config.py`
- `backend/src/libtv_agent/domain/enums.py`
- `backend/src/libtv_agent/domain/models.py`
- `backend/src/libtv_agent/adapters/openai_analysis.py`
- `backend/src/libtv_agent/services/ai_usage.py`
- `backend/src/libtv_agent/services/analysis.py`
- `backend/src/libtv_agent/services/prompt_revision.py`
- `backend/src/libtv_agent/api/tasks.py`
- `backend/alembic/versions/c8e9f0a1b2c3_ai_usage_guard.py`
- `frontend/src/api.ts`
- `backend/tests/test_ai_usage.py`
- `backend/tests/test_ai_usage_workflows.py`
- `backend/tests/test_cutflow_handoff.py`
- `docs/CHANGELOG.md`
- 本报告

Migration `c8e9f0a1b2c3` 的 parent 是当前实际 Cutflow head
`c7d8e9f0a1b2`，没有覆盖或重写未跟踪 Cutflow migration。

## 测试

testing 工作树使用隔离 SQLite、Fake/Replay 或 monkeypatch Provider，不读取真实
`.env`，不调用真实 OpenAI，不重启服务：

- `backend/tests/test_ai_usage.py`：5 passed；
- `backend/tests/test_ai_usage_workflows.py`：6 passed；
- `backend/tests/test_workflow_integration.py -k "analysis or prompt"`：通过；
- focused 源码、迁移和测试 Ruff：通过；
- Alembic heads：单一 `c8e9f0a1b2c3`；
- migration integrity 检查覆盖 Cutflow 和三张 AI usage 表。

覆盖内容包括额度不足时 Provider 调用次数为零、分析和 Prompt Assistant 幂等重放、
ADVISE/REGENERATE 门禁、Fake 离线结算、明确未提交释放、timeout/UNKNOWN 保留、
用户和全局额度并发竞争、持久化状态重启读取，以及 Prompt Assistant 前端请求头。

## 发现问题

- 既有 Cutflow 测试固定断言旧 head；已更新为新的单一 head，并额外确认 AI usage
  三张表升级存在。
- 隔离 SQLite 的并发写入通过；尚未验证 PostgreSQL、多 worker、崩溃恢复和正式运行时。
- 本包没有把 Feedback Learning 接入额度门，避免扩大入口范围；下一包处理。
- 风险单位是内部防护单位，不是报价或人民币成本；真实价格查询和复杂账单未实现。

## 下一步

- 在独立授权下补 PostgreSQL、多 worker、重启恢复和正式配置验收。
- 由下一包决定 Feedback Learning 是否复用同一额度服务。
- 代码同步不代表生产迁移、服务部署、Provider 开关或付费调用授权。
