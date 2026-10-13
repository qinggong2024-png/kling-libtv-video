# Sprint Report：Creative Workflow MVP-7B 编排服务

日期：2026-10-12
范围：将 MVP-6A Reality Loop Gate 接入独立、Provider-free 的 Creative 编排 facade

## 完成

- 新增独立 `creative_workflow_orchestrator` 服务，消费已确认的
  Loop Authorization、Product、Direction、DNA/Reality、TEXT_PACKAGE、E1 和
  CRITIC 快照。
- 按 `Product → Direction → DNA_REALITY → TEXT_PACKAGE → AUTHORIZATION → E1 →
  CRITIC → TARGETED_REVISION` 顺序委托 MVP-6A gate 做单步自主决策。
- 输出不可执行的下一阶段 command、stop/wait reason、不可变 revision summary 和
  audit event。
- revision 只包含父版本、hash、变更模块与因果变量摘要，不包含 Prompt 正文，
  不修改 Prompt，不调用模型或 Provider。
- 明确默认关闭、`max_revisions <= 2`、调用/费用上限、`UNKNOWN` /
  `WRITE_UNCERTAIN` 对账等待、锁项冲突、模块白名单和人工审核边界。

## 修改

仅新增以下白名单文件：

- `backend/src/libtv_agent/services/creative_workflow_orchestrator.py`
- `backend/tests/test_creative_workflow_orchestrator.py`
- `docs/SPRINT_REPORT_CREATIVE_WORKFLOW_MVP7B_20261012.md`

未修改：

- MVP-6A 的 `creative_reality_loop_gate.py`、`reality_loop.py` 及其测试；
- 现有 `creative_workflow.py`、Creative API、数据库、迁移、前端和 Provider adapter；
- `docs/ACTIVE_WORK.md`、`docs/CHANGELOG.md`；
- `.env`、密钥、缓存、运行时状态和构建产物。

## 测试

testing 结果：

- 固定模块顺序和不执行 command 的边界；
- Critic 失败证据只路由到一个允许的 Scene/Reality/Composition 模块；
- Product/锁项冲突、模块白名单、UNKNOWN/WRITE_UNCERTAIN 对账等待；
- 默认关闭、修订上限、不可变 revision 摘要；
- AI `NO_ACTION` 仍要求人工审核，绝不写 `QUALIFIED`；
- audit event 可重复、可序列化，并明确未调用 Provider、未写生产。

- `pytest backend/tests/test_creative_workflow_orchestrator.py
  backend/tests/test_creative_reality_loop_gate.py -q`：`34 passed`。
- scoped Ruff：`All checks passed`。
- scoped `compileall`：通过。
- scoped `git diff --check`：通过。

实际 `main` 独立复验：

- 实际目录：`C:\Users\Reel\Documents\libtv-auto-main-sync`，分支 `main`。
- 同一专项 pytest：`34 passed`。
- scoped Ruff：`All checks passed`。
- scoped `compileall` 和 `git diff --check`：通过。
- 三份白名单文件 SHA-256 与 testing 完全一致。

## 发现问题

- 本包证明的是服务端编排决策和审计输出，不是 worker 接线、持久化、Provider
  调用、费用扣账或真实像素质量证明。
- `revision_summary` 是不可变元数据摘要；未来执行器仍需在独立包中依据授权重新
  编译新 Prompt/Package，并继续通过既有 E1/Provider/人工审核边界。
- AI `NO_ACTION` 仅代表没有可操作的 Critic finding，仍必须进入人工审核。

## 下一步

- 如需继续，另立接线包处理持久化、恢复、真实 Critic 能力和 worker/Provider
  执行边界；本包不自动扩大生产权限。

## 同步

同步成功：仅推广本包三个白名单文件；未修改 MVP-6A、现有 creative workflow/API、
数据库、前端、Provider adapter、`docs/ACTIVE_WORK.md` 或 `docs/CHANGELOG.md`。
