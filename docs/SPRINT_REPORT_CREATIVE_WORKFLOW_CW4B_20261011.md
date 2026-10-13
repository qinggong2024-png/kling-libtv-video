# Sprint Report：Creative Workflow CW-4B 有界自主真实性循环策略

日期：2026-10-11

## 完成

- 新增与现有服务解耦的纯策略模块
  `backend/src/libtv_agent/creative/reality_loop.py`。
- 固定并校验执行顺序：
  `Product → Direction → DNA/Reality → Text Package → Authorization → E1 → Critic → Targeted Revision`。
- 将 Reality 六维顺序作为共享常量暴露：
  `Camera → Lighting → Composition → Human Behavior → Environment → Imperfection`。
- 默认关闭真实性循环；启用时约束 `max_revisions <= 2`，并逐个候选检查调用次数、总成本、授权有效期和用户停止。
- 将 `UNKNOWN` / `WRITE_UNCERTAIN` 转为只等待对账的不可变决定，不允许自动重试或替代生成。
- 支持像素未验证、无进步、锁项、允许模块白名单和超限停止。
- 每轮只输出一个最重要的未锁因果变量，使用稳定严重度排序，修订决定携带单一模块与变量。
- AI 批评器只接受 `NEEDS_REVISION`、`NO_ACTION`、`UNVERIFIED`，不产生人工资格结论；无动作时仍转人工审核。
- 使用冻结 dataclass 和 tuple 输入/输出，策略函数无 Provider、数据库、后台 Worker 或持久化副作用。

## 修改

仅修改 CW-4B 独占白名单：

- `backend/src/libtv_agent/creative/reality_loop.py`
- `backend/tests/test_creative_reality_loop.py`
- `docs/SPRINT_REPORT_CREATIVE_WORKFLOW_CW4B_20261011.md`

未修改：

- 现有 workflow/service；
- API、schema、OpenAPI、迁移和前端；
- 其他并行包文件；
- `.env`、密钥、缓存、运行时状态和构建产物。

## 测试

testing 分支聚焦验证：

```text
.venv\Scripts\python.exe -m ruff check backend/src/libtv_agent/creative/reality_loop.py backend/tests/test_creative_reality_loop.py
.venv\Scripts\python.exe -m pytest backend/tests/test_creative_reality_loop.py -q
```

结果：

- Ruff：`All checks passed`，退出码 `0`。
- pytest：`25 passed`，退出码 `0`。
- 测试覆盖固定顺序、默认关闭、授权边界、预算/调用限制、过期、
  停止、UNKNOWN/WRITE_UNCERTAIN、像素未验证、锁项/模块白名单、
  单变量选择、连续无进步、修订上限、不可变输入输出和确定性属性式风格检查。

## 发现问题与限制

- 本模块尚未接入 `services/creative_workflow.py` 或任何 API 运行路径。
- 本轮不证明 D4/E1 文字合同接线、不证明数据库事务/崩溃恢复、不证明真实像素 Critic 能力，也不调用 Provider 或付费服务。
- 纯策略返回的是下一步建议和停止/等待原因；调用、计费、对账、幂等和持久化仍必须由后续服务接线包实现。
- AI `NO_ACTION` 只表示没有可操作的批评项，输出仍标记需要人工审核，不能写入人工资格状态。

## 下一步

- 由 PM 在 testing 通过后将本三文件增量同步至实际 `main` 并独立复验。
- 只有后续明确接线、持久化和恢复验证完成后，才可讨论项目级自主真实性循环可用性。

## 同步

testing 已完成验证。实际 `main` 的局部同步和独立复验结果见下方；本报告不宣称
`INTEGRATION_VERIFIED`、`PRODUCTION_LOOP_READY` 或 `PRODUCTION_READY`。

## 实际 main 复验

实际生产源码目录：
`C:\Users\Reel\Documents\libtv-auto-main-sync`（分支 `main`）。

仅同步本报告、纯策略模块和专属测试三份文件；保留 main 其他生产差异，
不覆盖 `.env`、密钥、缓存、运行时状态或构建产物。

同步后独立运行同样命令：

- Ruff：`All checks passed`，退出码 `0`。
- pytest：`25 passed`，退出码 `0`。

因此 CW-4B 的纯策略模块在 testing 和实际 main 均完成 scoped 验证；
该结论不代表服务运行路径已接入。
