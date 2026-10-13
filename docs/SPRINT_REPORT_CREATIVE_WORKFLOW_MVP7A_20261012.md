# Sprint Report · Creative Workflow MVP-7A

日期：2026-10-12  
范围：MVP-4B durable ticket、MVP-5B durable input lease 与 MVP-5A image executor 的服务层接线  
testing：`E:/Projects/libtv自动化生成`，`codex/testing`  
实际 main：`C:/Users/Reel/Documents/libtv-auto-main-sync`，`main`

## 完成

新增 `creative_image_workflow_orchestrator`，只支持 Creative
`FIRST_FRAME/image_edit` 的单样本路径：

```text
durable submission ticket
→ durable input lease create/revalidate
→ durable input materialize
→ executor PREPARED/REPLAYED/TEST_DOUBLE
```

服务层审计摘要固定包含：

- ticket、lease、request/evidence/preflight hash 和幂等键；
- `DURABLE_TICKET`、`DURABLE_INPUT_LEASE`、`IMAGE_EXECUTOR` 阶段状态；
- durable input manifest、manifest hash 和整体 summary hash；
- `UNKNOWN` 只允许对账，`FAILED` 必须使用新幂等键，停止任务和停止票据不再沿原键执行；
- dry-run、replay、test-double 的 `OFFLINE_SYNTHETIC_ONLY` 与
  `deliverable_eligible=false`。

live 分支在编排层再次检查 feature flag、`staging/production` 环境、管理员开关、
人工确认、approval、quote、预算/许可预检、付费开关和暂停状态；MVP-7A 最后仍以
`LIVE_EXECUTION_DISABLED_MVP7A` 安全失败，不调用真实 adapter。

## 修改

仅新增白名单文件：

- `backend/src/libtv_agent/services/creative_image_workflow_orchestrator.py`
- `backend/tests/test_creative_image_workflow_orchestrator.py`
- `docs/SPRINT_REPORT_CREATIVE_WORKFLOW_MVP7A_20261012.md`

未修改：

- `docs/ACTIVE_WORK.md`
- `docs/CHANGELOG.md`
- API、OpenAPI、前端和数据库迁移；
- 旧 `image_generations` 业务服务；
- Provider adapter、quota、ledger、attempt、billing 和旧任务入口。

## 测试

testing：

- MVP-7A orchestrator 专项：`7 passed`；
- MVP-7A 与 MVP-4B/MVP-5A/MVP-5B 组合：`30 passed`；
- scoped Ruff：通过；
- 白名单 `git diff --check`：通过；
- dry-run/replay 禁止 adapter 调用；
- test-double 只允许显式替身；
- live 所有前置门满足时仍在 MVP-7A 安全闸停止；
- UNKNOWN、FAILED、USER_STOPPED 不沿原幂等键重提；
- 未写旧 image generation、quota、ledger、attempt 或计费记录。

实际 main 独立复验：

- 同一白名单文件同步后重新运行 MVP-7A 专项与组合回归；
- scoped Ruff、`git diff --check` 和三份白名单 SHA-256 一致性检查；
- 未执行生产迁移、部署、服务重启或真实 Provider POST。

## 发现问题

- 本包复用 MVP-5A executor 的 ticket manifest 约束。durable lease 物化后会把已验证
  的字节回填到 ticket 原 manifest 路径，以满足不可变 ticket hash；不修改 ticket
  快照，也不把 durable object key 伪装成新的 ticket 输入。
- 本包仍未证明 PostgreSQL 多 worker、跨进程崩溃窗口、真实费用原子化、Provider
  接收证据、真实像素复核或人工 QUALIFIED。
- test-double 结果只证明调用边界，不代表真实 Provider 成功或可交付。

## 下一步与限制

后续真实提交包仍需单独授权，并补齐真实 Provider POST、提交领取/费用原子事务、
UNKNOWN 对账、进程恢复、真实输出审核和交付门。不得因本包 dry-run/replay 或
test-double 通过而开放 live。

## 同步

testing 验证通过后，只将上述三份白名单文件同步到实际 `main`，保留 main 的生产
专属差异、未提交改动、密钥、`.env`、缓存、运行时状态和构建产物。main 将独立
复验专项、组合回归、scoped Ruff、空白检查和文件哈希；不执行生产迁移、部署、
服务重启或真实 Provider 调用。
