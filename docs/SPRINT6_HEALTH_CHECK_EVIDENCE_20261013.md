# Sprint 6 健康检查专项验收证据

日期：2026-10-13
范围：Backend Runtime Stability Audit 的 health check 子任务

## 结论

现有健康检查实现满足本子任务要求，无需修改
`backend/src/libtv_agent/api/health.py`、router 或 app。

已验证：

- `GET /api/v1/health/live` 在不依赖数据库、schema 或 Provider 的情况下返回
  `200 {"status":"ok"}`。
- `GET /api/v1/health/ready` 先执行只读 `SELECT 1`，再检查数据库表和 Alembic
  head；schema 完整时返回 200，schema 缺失或数据库不可用时返回稳定的 503。
- `/health/live` 和 `/health/ready` 仅接受 GET；POST 返回 405。
- readiness 检查不会执行 Alembic migration、Provider availability probe、Provider
  credential verification、付费请求或数据库写入。
- `health` router 已由 `backend/src/libtv_agent/api/router.py` 挂载到
  `/api/v1/health`。

## 当前运行链路

```text
GET /api/v1/health/live
  -> liveness-only response

GET /api/v1/health/ready
  -> request.app.state.database.session_factory()
  -> SELECT 1
  -> inspect_database_schema(connection)
  -> table presence + Alembic head comparison
  -> 200 ready / 503 degraded
```

`inspect_database_schema` 只读取数据库 inspector、Alembic migration context 和
项目 metadata；health endpoint 不调用 migration command。

## API 状态与输出契约

| Endpoint | Healthy | Not ready / unavailable |
| --- | --- | --- |
| `GET /api/v1/health/live` | `200 {"status":"ok"}` | 不依赖基础设施 |
| `GET /api/v1/health/ready` | `200 {"status":"ok","checks":{"postgresql":"ok","databaseSchema":"ok"}}` | `503`，分别返回 `databaseSchema: outdated` 或 `postgresql: unavailable` |

Schema 过期时还返回 `databaseSchema.currentRevisions`、`expectedRevisions` 和
`missingTables`，便于运行时诊断。

## 测试与结果

testing 分支：

```text
backend/tests/test_health.py
7 passed
Ruff: passed
```

专项测试覆盖：

- live endpoint 的基础设施隔离；
- provider 配置热加载异常不影响 live；
- system status 的 source/schema/config revision 证据；
- ready 的完整 schema；
- ready 的缺表/schema 过期；
- health endpoint 的 GET-only 约束；
- ready 只读 SQL、无 migration、无 Provider/付费副作用；
- 数据库不可用时稳定返回 503。

## 未验证部分与剩余风险

- 未连接真实 PostgreSQL、真实生产 schema 或正式服务。
- 未执行 Alembic migration；本子任务只验证 readiness 能识别 schema 状态。
- 未调用任何真实 Provider，未产生付费请求，未写入生产数据库。
- 完整 Product → Brand DNA → Creative Package → Image Adapter → Video Adapter →
  Human Review workflow 由 Sprint 6 其他专项测试覆盖；本文件只记录 health
  endpoint 证据。

## 改动范围

- `backend/tests/test_health.py`：新增 2 个专项契约/副作用测试。
- `docs/SPRINT6_HEALTH_CHECK_EVIDENCE_20261013.md`：新增本验收证据。
- `backend/src/libtv_agent/api/health.py`：未修改。
- `backend/src/libtv_agent/api/router.py`：未修改。
- `backend/src/libtv_agent/app.py`：未修改。
