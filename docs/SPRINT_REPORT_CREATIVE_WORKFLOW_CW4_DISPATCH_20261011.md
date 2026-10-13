# Sprint Report：Creative Workflow CW-4 并行小包验收

日期：2026-10-11
性质：PM 调度与独立验收记录，不是生产上线批准。

## 结果

本轮将较大的后端任务拆为三个互不争用的小包，分别覆盖运行接线、循环策略和恢复证据：

| 包 | PM 验收结果 | 证据 |
| --- | --- | --- |
| CW-4A | 通过，释放 D4/E1 文字合同运行接线白名单 | testing/main 各 `75 passed`，Ruff 通过 |
| CW-4B | 通过，释放有界自主真实性循环纯策略白名单 | testing/main 各 `25 passed`，Ruff 通过 |
| CW-4C | 通过，仅释放隔离 SQLite 恢复证据白名单 | testing/main 各 `5 passed`，Ruff 通过，runner 网络拒绝 |

## CW-4A 验收

- D4 在选方向和修订编译后冻结 plan、package、facts 和 Prompt Registry 完整上下文。
- E1 在生成/修订产生费用、attempt、候选前重新校验实际包。
- Prompt、事实、锁、Registry、Reality 篡改均被 `TEXT_CONTRACT_REJECTED` 阻断，执行路径不现场重写 Prompt。
- 两侧实现、测试和报告 SHA 已核对一致。

这解决的是“文字合同模块存在但未接线”的问题，不证明真实 Provider 已接收相同 Prompt，也不证明像素真实性提升。

## CW-4B 验收

- 固定 `Product → Direction → DNA/Reality → Text Package → Authorization → E1 → Critic → Targeted Revision` 顺序。
- 默认关闭自主循环，修订上限不超过 2；检查授权有效期、调用次数、总成本、停止、未知结果、无进步、锁项和模块白名单。
- `UNKNOWN` / `WRITE_UNCERTAIN` 只产生等待对账决定，AI Critic 不产生人工 `QUALIFIED`。

该模块是纯策略，尚未接入服务、Provider、账本或后台 worker；不能宣称自主循环已在生产执行。

## CW-4C 验收

- 同命令重放不重复创建候选或计费。
- 未知状态只能经明确对账恢复。
- stop 阻止新轮次并保留既有证据。
- app/engine 重建后可从持久快照恢复。

未覆盖 PostgreSQL 并发、跨进程崩溃窗口、真实账本事务边界和 Provider UNKNOWN 结算。观察项是 stop 当前不单独追加 `CreativeRecord`，后续另立窄修复包。

## 同步与限制

- testing：`E:\Projects\libtv自动化生成`，分支 `codex/testing`。
- 实际 main：`C:\Users\Reel\Documents\libtv-auto-main-sync`，分支 `main`。
- 三个包均已先在 testing 验证，再局部同步并在实际 main 独立复验。
- 未执行生产迁移、部署、服务重启、真实 Provider 或付费调用。
- 现有用户未提交改动、`.env`、缓存、构建产物和 ZIP 均未同步。

## 下一步建议

1. 另立窄包补 stop 独立审计事件，并做 PostgreSQL/多 worker 竞争专项。
2. 将 CW-4B 纯策略接入服务编排，但只允许在 CW-P04/P08 成本与质量门通过后启用。
3. 在真实像素输入和 Provider 接收证据可用前，保持自动修订关闭，人工审核仍是 `QUALIFIED` 唯一门。
