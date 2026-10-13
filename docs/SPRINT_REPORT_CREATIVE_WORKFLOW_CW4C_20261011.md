# Creative Workflow CW-4C Sprint Report

日期：2026-10-11
范围：事务 / 恢复证据窄包
状态：隔离证据包通过；不代表 PG/生产就绪

## 完成

- 新增隔离 SQLite 合同测试：
  - 同一命令重放返回原响应，不重复计费、不重复创建候选或图片批次；
  - `UNKNOWN` / `WRITE_UNCERTAIN` 阻断新的执行动作，缺少 reconcile 证据不能清除未知状态；
  - `stop` 阻止新的修订轮次，并保留已有候选与 append-only 审计记录；
  - 关闭并重新构建 app / database engine 后，从持久 snapshot 恢复 UNKNOWN，再 reconcile 并继续生成。
- 新增 `scripts/run_creative_recovery_tests.py`：
  - 只运行 CW-4C 测试文件；
  - 使用临时证据目录和隔离 SQLite；
  - 注入网络拒绝 guard；
  - pytest 非零结果原样返回，不吞失败。

## 修改

仅限以下文件：

- `backend/tests/test_creative_workflow_recovery_contract.py`
- `scripts/run_creative_recovery_tests.py`
- `docs/SPRINT_REPORT_CREATIVE_WORKFLOW_CW4C_20261011.md`

未修改 Creative Workflow service、migration、schema、OpenAPI、前端或生产配置；未连接 PostgreSQL、正式服务或 Provider。

## 审查结论

- `CreativeTask.snapshot_json` 与 `state_version` 可在 SQLite app 重建后恢复；
- `CreativeCommand` 的 `(task_id, command_key)` 幂等记录可让同命令重放返回原结果；
- `UNKNOWN` / `WRITE_UNCERTAIN` 保留任务级成本预占，只有显式 `reconcile_not_submitted=true` 才释放并允许继续；
- `stop` 的状态标记和既有记录不会被清除，后续新生成/修订被拒绝；
- 当前 service 对 UNKNOWN 允许 `stop` 和 `revoke_asset` 作为终止动作；CW-4C 将“只能 reconcile”解释为“只有 reconcile 能清除 UNKNOWN 并恢复新执行”，而非禁止终止动作。

已知服务观察项：

- `stop` 分支没有单独追加 `CreativeRecord` 审计事件；本包只证明 stop 不删除既有 append-only 证据，不修改 service。若业务要求每次 stop 都有独立事件，应另立修复包。
- 本包只证明隔离 SQLite、单进程串行请求和 app/engine 重建；不证明 PostgreSQL 并发、跨进程崩溃窗口、真实账本事务边界或 Provider UNKNOWN 结算。

## 测试

### testing

结果：通过。

```powershell
.venv/Scripts/python.exe -m ruff check backend/tests/test_creative_workflow_recovery_contract.py scripts/run_creative_recovery_tests.py
.venv/Scripts/python.exe scripts/run_creative_recovery_tests.py --root E:\Projects\libtv自动化生成 --evidence-dir <external-evidence-dir>
```

- scoped Ruff：通过；
- recovery runner：`5 passed`，exit code `0`；
- runner 约束：`network=denied`、`database=isolated-sqlite`；
- runner source hash：`3ab68831ad89fc2a863f2aa95c285408ddca1137392e26327cfbb00d954ef404`；
- pytest JUnit：`F:\Temp\creative-recovery-mypybi18\junit.xml`。

### 实际 main

结果：通过。同一 scoped Ruff 与 runner，根目录为：

```text
C:\Users\Reel\Documents\libtv-auto-main-sync
```

- scoped Ruff：通过；
- recovery runner：`5 passed`，exit code `0`；
- runner 约束：`network=denied`、`database=isolated-sqlite`；
- runner source hash：`31c75f870071fc987ab8fa7e1b4f2a7a799bd32db0b65997938517728a7a9bbf`；
- pytest JUnit：`F:\Temp\creative-recovery-b7snqkon\junit.xml`。
- 两个 source hash 不同是预期的：runner 对既有 Creative Workflow service 源码做了指纹，testing/main 当前 service 存在既有差异；本 CW-4C 三项交付文件 hash 一致。

### 交付文件哈希

testing 与实际 main 的以下文件 SHA-256 均一致：

| 文件 | SHA-256 |
| --- | --- |
| `backend/tests/test_creative_workflow_recovery_contract.py` | `AEF48BBFDB7AE72354720F13312D3D373C04DBC7BC2354B21ADD4C69D3DCD880` |
| `scripts/run_creative_recovery_tests.py` | `31B53261B8AD90566AB75323F92C4C9214168D05E2FCA51730466956714FBAA3` |

## 发现问题

本包没有运行失败或阻塞。代码审查仍保留以下 service 观察项：`stop` 分支没有单独追加 `CreativeRecord` 审计事件；本包只证明 stop 不删除已有 append-only 证据，不修改 service。若业务要求每次 stop 都有独立事件，应另立修复包。

## 下一步

- 由 PM 独立复验两侧测试和 Ruff；
- 记录两侧文件哈希、runner source hash、pytest 数量与失败详情；
- 若两侧通过，只释放 CW-4C 的 SQLite 事务/恢复证据白名单，不宣称 PG、生产恢复或生产就绪；
- 若出现 service 缺陷，只在本报告登记，另行开包修复。

## 同步状态

- testing：三项 CW-4C 文件已新增，目标文件均为未提交状态；未触碰其他工作区改动。
- 实际 main：同三项文件已局部同步，目标文件均为未提交状态；未触碰其他工作区改动。
- 未执行 commit、生产迁移、部署、服务重启、真实 Provider 或付费调用。
