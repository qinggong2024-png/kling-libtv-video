# Sprint Report · Creative Workflow MVP-5B

日期：2026-10-12  
范围：为 MVP-4A/4B 补齐 durable Provider input lease/materialization 合同  
testing：`E:/Projects/libtv自动化生成`，`codex/testing`  
实际 main：`C:/Users/Reel/Documents/libtv-auto-main-sync`，`main`

## 完成

新增独立 durable input lease 服务和最小持久化表。它把 MVP-4B
`ProviderSubmissionTicket` 中只在临时 preflight lease 期间有效的本地路径，
复制为稳定的本地 object store 对象，并保存可跨 session 重放的 manifest：

```text
MVP-4B durable ticket
→ 重新执行 MVP-3B preflight / 人工许可 / 资格证据检查
→ 校验临时输入存在、媒体类型和字节 SHA-256
→ 复制到确定性的 durable object key
→ 持久化 owner/task/package/shot/request/evidence、对象和许可证据
→ 重新校验来源后返回 ACTIVE lease
→ 提交前重新物化为短生命周期本地文件
```

Lease 状态为 `ACTIVE`、`MATERIALIZED`、`EXPIRED`、`REVOKED`。同一
idempotency key 的相同 ticket 重放原 lease；不同 ticket/hash 返回冲突。租约
过期、授权/资格/来源变化、对象缺失、媒体类型变化或 durable 字节哈希变化会
拒绝使用，并将活动租约撤回。owner 不匹配不会泄露其他 owner 的 lease。

每个输入绑定角色、顺序、adapter field、原始 `object_key`、durable
`object_key`、SHA-256、媒体类型、字节大小、许可 ID、许可证据 ID 和许可有效期。
请求的 `request_hash`、`evidence_hash`、Provider 资格与人工许可仍由
MVP-3B 现有 preflight 真源复核；本包没有另造资格或授权快捷路径。

本包只写本地 object store 和 input lease 表，不调用 Provider、不上传远端、不
预占/扣除 quota、不写 ledger/attempt、不创建 image generation 记录，也不修改
旧 image/video 执行路径。

## 修改

仅新增以下白名单文件：

- `backend/src/libtv_agent/creative/provider_input_lease.py`
- `backend/src/libtv_agent/services/creative_provider_input_lease.py`
- `backend/alembic/versions/e5f6a7b8c901_creative_provider_input_leases.py`
- `backend/tests/test_creative_provider_input_lease.py`
- 本报告

未修改 `domain/models.py`、API、OpenAPI、旧 `image_generations`、
Provider adapter、MVP-4A/4B 文件、`docs/ACTIVE_WORK.md`、
`docs/CHANGELOG.md`、前端或 `.env`。

## 测试

testing 专项：

- MVP-5B：`5 passed`；
- 覆盖 durable copy、跨 session replay、`ACTIVE → MATERIALIZED`、同键冲突、
  owner 隔离、过期、撤回、源字节篡改、媒体类型和迁移结构；
- scoped Ruff：通过；
- 白名单 `git diff --check`：通过；
- `uv run alembic heads`：`e5f6a7b8c901 (head)`。

实际 main 独立复验：

- MVP-5B：`5 passed`；
- 同一组合回归：`263 passed`；
- scoped Ruff、白名单 `git diff --check` 和 Alembic head：通过；
- 五个白名单文件 SHA-256 与 testing 一致。

Creative 组合回归：

- MVP-5B、MVP-4A、MVP-4B、MVP-3B/preflight、Provider request、
  image bridge、media isolation、image generation batches：全部通过；
- 组合白名单合计：`263 passed`；
- 本包迁移专项确认 `provider_input_lease` 表、owner/task/package/shot、
  request/evidence hash、manifest、状态、过期时间和三项幂等唯一约束。

既有迁移完整性专项仍有 2 个失败：

- `test_fact_and_history_update_delete_triggers_reject_direct_sql`
- `test_creative_command_delete_trigger_rejects_direct_sql`

两项失败都发生在既有测试使用的 `d1e2f3a4b506` fixture 历史触发器断言，
与 MVP-5B 新表和新迁移无关；本包没有修改其文件或历史迁移。

## 发现问题

- SQLite 专项证明了单机数据库 session 的 durable replay 和唯一幂等插入；
  没有证明 PostgreSQL 多 worker 的锁等待、并发 claim、跨进程崩溃窗口或
  服务重启恢复。
- 本包只建立 durable 输入和使用前重验；真实 Provider 接线、Provider 接收
  证据、费用原子化、UNKNOWN 对账和像素质量仍未完成。
- durable object copy 失败或来源在复制后变化时可能留下未引用的本地对象，
  需要后续保留/清理策略包处理；lease 不会因此被标为可用。

## 同步

testing 验证通过后，只同步以上五个白名单文件到实际 `main`，保留 main 的
生产专属差异、未提交改动、密钥、`.env`、缓存、运行时状态和构建产物。
同步不执行生产迁移、部署、服务重启或真实 Provider 调用。
