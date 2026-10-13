# Sprint Report: Creative Workflow Migration Integrity Repair

日期：2026-10-12  
范围：修复 MVP-5B 暴露的 Creative Workflow 历史迁移触发器回归

## 完成

- 保留历史迁移 `d1e2f3a4b506` 不变。
- 使用后续迁移 `d2f3a4b5c607` 补齐：
  - `product_version` 的直接 DELETE 拒绝；
  - `creative_command` 的直接 UPDATE/DELETE 拒绝。
- 将历史数据升级完整性 fixture 的验证终点提升到 `d2f3a4b5c607`，使断言覆盖实际修复后的 schema，而不是停在已知缺口的 d1 基线。
- 保留 d1 → d2 的 downgrade 边界测试，确认回退到 d1 后 d1 原有保护仍在，d2 新增保护按预期移除。

## 原因与边界

MVP-5B 报告中的两个失败并非新 durable input lease 表引入，而是完整性测试在
`d1e2f3a4b506` 停止升级。d1 只创建了 ProductVersion 事实 UPDATE 和部分历史表
保护；缺失的 ProductVersion DELETE 与 CreativeCommand 不可变保护由后续 d2
迁移追加。因此不能修改 d1 来改变历史 schema，也不能删除或放宽原失败断言。

## 修改

- `backend/alembic/versions/d2f3a4b5c607_creative_integrity_repair.py`
- `backend/tests/test_creative_migration_integrity.py`
- `backend/tests/test_creative_migration_repair.py`
- 本报告

未修改 d1 历史 migration、业务模型、API、Provider、前端、旧图片/视频路径、
MVP-7 文件、真实 `.env` 或生产运行状态。

## 测试

testing (`codex/testing`)：

- `python -m pytest backend/tests/test_creative_migration_integrity.py -q`
- `python -m pytest backend/tests/test_creative_migration_repair.py -q`
- `python -m ruff check backend/alembic/versions/d2f3a4b5c607_creative_integrity_repair.py backend/tests/test_creative_migration_integrity.py backend/tests/test_creative_migration_repair.py`
- `alembic heads`：唯一 head 为 `e5f6a7b8c901`

验证重点：

- d0 → d1 → d2 带旧数据升级后，事实/历史行哈希保持不变；
- ProductVersion UPDATE/DELETE 和 CreativeCommand UPDATE/DELETE 均被直接 SQL 拒绝；
- d2 downgrade 不删除 d1 原有保护；
- SQLite 迁移路径通过；未执行 PostgreSQL 实例验证。

未调用 Provider、未扣费、未执行生产迁移、部署、服务重启或真实数据写入。

## 同步

testing 验证通过后，只同步上述迁移、迁移测试和本报告到实际 `main` 工作树，
保留 main 的生产专属差异、未提交改动、密钥、`.env`、缓存、运行时状态和构建
产物。同步不代表线上部署或执行生产迁移。
