# Sprint Report · Creative Workflow MVP-6A

日期：2026-10-12
范围：独立 Creative Reality Loop 运行门和策略合同
testing：`E:/Projects/libtv自动化生成`，`codex/testing`
实际 main：`C:/Users/Reel/Documents/libtv-auto-main-sync`，`main`

## 完成

新增纯合同服务 `creative_reality_loop_gate`，把有限真实性循环提升为可独立测试的运行门。它按以下顺序返回一个下一步决策：

```text
Product → Direction → DNA_REALITY → TEXT_PACKAGE
→ AUTHORIZATION → E1 → CRITIC → TARGETED_REVISION
```

合同吸收并显式记录：

- 默认关闭和独立人工授权；
- `max_revisions <= 2`、`max_calls`、`max_total_cost_micros`、授权有效期；
- Product/brand lock、模块白名单、Scene/Reality/Composition 锁冲突；
- Reality 六维固定顺序及每维证据/N/A 原因；
- Scene 与 Composition 分层证据；
- Prompt Preservation、父 revision、不可变 package/prompt revision 摘要；
- `UNKNOWN` / `WRITE_UNCERTAIN` 只等待对账，不重试或启动替代生成；
- 缺像素、无进展、超限、预算、过期、未知和锁冲突停止原因；
- AI 结论保持 `UNVERIFIED` / 人工待审，不写 `QUALIFIED`；
- 只输出下一步、停止/等待原因和审计摘要，审计明确未调用 Provider、未写生产。

## 修改

仅新增以下白名单文件：

- `backend/src/libtv_agent/services/creative_reality_loop_gate.py`
- `backend/tests/test_creative_reality_loop_gate.py`
- `docs/SPRINT_REPORT_CREATIVE_WORKFLOW_MVP6A_20261012.md`

没有修改现有 `backend/src/libtv_agent/creative/reality_loop.py`，没有修改 API、
OpenAPI、前端、数据库、migration、Provider adapter、`.env`、
`docs/ACTIVE_WORK.md` 或 `docs/CHANGELOG.md`。

## 测试

testing：

- MVP-6A 专项测试覆盖固定顺序、六维 Reality、证据依赖、授权/预算/调用上限、
  不确定执行等待、Prompt Preservation、锁冲突、模块白名单、无进展、不可变
  revision 摘要和人工资格边界。
- `backend/tests/test_creative_reality_loop_gate.py`：`23 passed`。
- 与既有 `backend/tests/test_creative_reality_loop.py` 隔离回归合计：`49 passed`。
- scoped Ruff、Python `compileall` 和 `git diff --check`：通过。

实际 main 独立复验：

- MVP-6A 专项：`23 passed`。
- scoped Ruff、Python `compileall` 和 `git diff --check`：通过。
- testing/main 三个白名单文件 SHA-256 一致。

## 发现问题

- 本包是运行门和策略合同，不接入现有 worker、Creative API、图片/视频服务或
  Provider adapter。
- 本包只消费调用方提供的像素验证标记；它不把结构化规则、Fake/Replay 或 AI
  `NO_ACTION` 当作真实像素能力或人工 `QUALIFIED`。
- 真实 Critic 是否能读取原图与输出像素、返回区域证据，仍需真实 Provider/模型
  授权与单独验证。
- 审计中的调用次数和成本是调用方快照，不执行预占、扣费、账本写入或生产持久化。

## 下一步

将运行门接入实际编排仍需单独包实施，继续保持默认关闭、人工授权、不可变包和
未知结果对账边界；接入前需补真实 Critic 能力、持久化/恢复和生产运行验证。
本包不代表项目已经接入自主生成循环，也不代表生产就绪或上线批准。

## 同步

testing 验证通过后，只同步上述三个白名单文件到实际 `main`，逐文件比较并保留
main 既有生产专属差异、未提交改动、密钥、`.env`、缓存、运行时状态和构建产物。
同步后在实际 main 独立运行本包专项测试、Ruff 和空白检查，并记录两侧文件哈希。
