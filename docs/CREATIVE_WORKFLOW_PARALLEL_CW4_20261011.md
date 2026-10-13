# Creative Workflow CW-4 小包并行调度

日期：2026-10-11
性质：任务分发与验收边界，不是上线批准或真实生成授权。

## 本轮目标

在 CW-3A/B/C 通过、CW-3E 修复并独立复验通过后，继续用窄范围小包推进 Creative Workflow：

1. 将文字完整性合同真正接入 D4/E1 运行路径；
2. 将插件的固定模块顺序和有限自主真实性循环固化为可测试纯策略；
3. 用隔离 SQLite 证明命令重放、UNKNOWN、停止和进程重建恢复边界。

本轮不调用真实 Provider、不执行生产迁移、不部署、不重启正式服务，不把 Fake/Replay 结果当作真实像素质量证据。

## 并行包

| 包 | 单一交付目标 | 独占写入范围 | 关键验收 |
| --- | --- | --- | --- |
| CW-4A | 接通 D4 冻结和 E1 校验文字合同 | `backend/src/libtv_agent/services/creative_workflow.py`、必要的 `creative/workflow.py` 辅助、专属集成测试、专属报告 | 冻结上下文可恢复；实际包被完整校验；事实/锁/Prompt/Registry/Reality 变化在运行路径阻断；不现场重写 Prompt |
| CW-4B | 固化有界自主真实性循环纯策略 | 新增 `backend/src/libtv_agent/creative/reality_loop.py`、专属测试、专属报告 | 固定阶段顺序；默认关闭；授权、预算、次数、过期、停止、UNKNOWN、无进步和模块白名单均可判定；不自动 QUALIFIED |
| CW-4C | 验证事务/恢复合同 | 新增恢复测试、定向 runner、专属报告 | 重放不重复候选/成本；UNKNOWN 只能对账；stop 保留审计并阻止新轮次；重建 app/engine 可继续持久快照 |

## 文件边界

- CW-4A 不修改迁移、schema、OpenAPI、前端和共享文档。
- CW-4B 不接入服务，不修改现有 workflow/service/schema。
- CW-4C 只新增严格测试和 runner，不修复服务缺陷；真实缺陷写报告。
- PM 独占本调度文档、`docs/ACTIVE_WORK.md`、本轮总报告和 CHANGELOG 登记。
- 任何窗口不得全树同步，不得覆盖实际 main 的生产专属差异。

## 执行规则

每个窗口先在 `codex/testing` 运行聚焦测试，再只同步自己的白名单到实际 `main` 并复验。报告必须写明：

- 修改文件和未修改文件；
- 测试命令及通过/失败数；
- testing/main 同步范围和保留差异；
- 未证明的 PostgreSQL、真实 Provider、真实像素和生产配置边界。

只有 CW-4A 通过后，才可以声称 D4/E1 运行路径具备文字合同门；CW-4B 通过只代表策略模块可用，不能声称后台自主循环已经接入；CW-4C 若发现缺陷，保持失败证据，不通过修改测试吞掉。

## 当前登记

| 包 | 窗口 | 状态 |
| --- | --- | --- |
| CW-4A | `01a12741-eb67-7273-9a50-c727626d9c8f` | PM 验收通过，运行接线白名单释放 |
| CW-4B | `01a12741-ed12-7f23-9eb9-13a2dd404aca` | PM 验收通过，纯策略白名单释放 |
| CW-4C | `01a12741-ee82-78e0-a7ee-85914c8e0416` | PM 验收通过，仅释放 SQLite 恢复证据 |

## 前置验收结果

- CW-3E：testing 和实际 main 各自 Ruff 通过、3 项迁移修复测试通过；`d2f3a4b5c607` 与 d1 兼容，不修改历史迁移。
- CW-3D 的 2 项失败仍保留为历史缺口证据，不被改写为通过。
- CW-3B 原先只证明纯模块；CW-4A 已补齐 D4/E1 运行接线并通过独立验收。

## PM 独立验收

- CW-4A：testing/main 各 75 项聚焦回归通过，Ruff 通过；D4 冻结、E1 实际包校验和篡改阻断已接入。
- CW-4B：testing/main 各 25 项纯策略测试通过，Ruff 通过；模块仍未接入服务运行路径。
- CW-4C：testing/main 各 5 项隔离恢复测试通过，Ruff 通过；未证明 PostgreSQL、多 worker 崩溃窗口或真实账本事务边界。
- 观察项：当前 `stop` 不单独追加 `CreativeRecord` 事件，但不会删除既有审计记录；另立窄修复包，不在 CW-4C 越界修改。
