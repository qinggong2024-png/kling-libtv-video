# Sprint Report：Creative Workflow CW-3A

日期：2026-10-10
范围：Fake 命令的预算、停止、创建重放和 ProductVersion 事实版本修复

## 完成

- UNKNOWN/WRITE_UNCERTAIN 对账同时释放授权级 `cost_micros` 和任务级 `total_cost_micros`，重复对账不会重复扣减或释放。
- `total_task_cap_micros=0` 按显式零预算执行；跨授权任务上限继续取历史上限与新授权上限的最大值。
- stop 后保持 `USER_STOPPED`；资产撤回后对账返回 `BLOCKED`，停止任务不能通过授权恢复生成。
- 带 `client_key` 的创建重放读取并返回首次保存的 201 body；同键异请求仍返回冲突。
- analyze 和 GroundedClaim 使用任务绑定 ProductVersion 的真实 `facts_revision`。

## 修改

- `backend/src/libtv_agent/services/creative_workflow.py`
- `backend/src/libtv_agent/api/creative_workflow.py`
- `backend/tests/test_creative_workflow_accounting.py`
- 本报告

未修改共享 ORM/schema/enums、迁移、OpenAPI、前端、旧测试文件或其他包文件。

## 测试

- 外部 cwd、临时 SQLite、Fake、`_env_file=None`：
  `uv run --project E:\Projects\libtv自动化生成 pytest E:\Projects\libtv自动化生成\backend\tests\test_creative_workflow_accounting.py E:\Projects\libtv自动化生成\backend\tests\test_creative_workflow.py`
  结果：25 passed。
- Creative Workflow 相关 Product 回归：
  `uv run --project E:\Projects\libtv自动化生成 pytest E:\Projects\libtv自动化生成\backend\tests\test_products.py`
  结果：3 passed。
- scoped Ruff：
  `uv run --project E:\Projects\libtv自动化生成 ruff check ...`
  结果：All checks passed。
- 未读取真实 `.env`，未连接生产数据库，未启动或停止服务，未调用真实 Provider 或付费能力。

## 发现问题

- 本包未证明 PostgreSQL 并发、跨进程崩溃恢复或真实账本事务边界；这些仍是后续专项缺口。
- Fake/Replay 通过不代表真实像素质量、Provider 接收或生产计费已验证。
- API schema 未改变，因此未生成 OpenAPI。

## 同步

- testing 已通过上述 28 项测试和 scoped Ruff。
- 实际 `main` 目录为 `C:\Users\Reel\Documents\libtv-auto-main-sync`；将逐文件比较后只同步本包四个白名单文件，保留其余生产差异。
- main 独立复验：Creative Workflow 25 passed，Product 3 passed，scoped Ruff 通过。
- testing/main 四个文件 SHA-256 一致：
  - `services/creative_workflow.py`: `4AA8A8A6E3D00463DB23BA377589ADACE3F1FC540932593D1B076AA42F9F876C`
  - `api/creative_workflow.py`: `2BCBE4BF1D59381A05B63B877F6F6F4D4DF55C3D41F04F2E09C905CEB03B8FD8`
  - `tests/test_creative_workflow_accounting.py`: `D35FD008DC3010B04EA15AD5AA8E8DAE0F458A9D29E9370BE75F9A20F4DC1969`
  - `docs/SPRINT_REPORT_CREATIVE_WORKFLOW_CW3A_20261010.md`: final hash recorded in the handoff message
- 推广成功：仅同步上述四个 CW-3A 白名单文件；未同步其他包、配置、缓存、构建产物或真实 `.env`。
