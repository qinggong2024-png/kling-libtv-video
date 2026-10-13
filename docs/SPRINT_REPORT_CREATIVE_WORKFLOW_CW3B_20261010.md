# Sprint Report：Creative Workflow CW-3B

日期：2026-10-10

## 完成

- 新增 `backend/src/libtv_agent/creative/text_contract.py`，提供纯函数 `validate_text_contract(plan, package, frozen_package, registry_snapshot, facts_snapshot)`。
- 以调用方提供的不可变 `frozen_package` 作为比较真源，覆盖事实版本/快照、商品来源 SHA、商品与用户锁、实际 Reality 六维、Prompt、包身份和 Prompt Registry 身份/内容哈希。
- 固定检查 Reality 顺序 `Camera → Lighting → Composition → Human Behavior → Environment → Imperfection`；缺维、乱序和无理由 `N/A` 拒绝，`Imperfection=none` 合法。
- 报告区分 `static_rule_validated`、`unverified` 和 `rejected`；旧 Registry 缺正文或 manifest 时只标记未证明。

## 修改

- 仅新增白名单文件：`backend/src/libtv_agent/creative/text_contract.py`、`backend/tests/test_creative_text_contract.py`、本报告。
- 未修改 `workflow.py`、`services/creative_workflow.py`、API、共享类型、迁移、OpenAPI 或公共文档。

## 测试

- 外部网络阻断 runner：
  `python scripts/run_creative_targeted_tests.py --root E:\Projects\libtv自动化生成 --evidence-dir E:\Codex\cw3b-testing-final2 --tests backend/tests/test_creative_text_contract.py`
  结果：`44 passed`，退出码 `0`；JUnit：`E:\Codex\cw3b-testing-final2\junit.xml`。
- `ruff check --config pyproject.toml --no-cache backend/src/libtv_agent/creative/text_contract.py backend/tests/test_creative_text_contract.py`：通过。
- testing 源码哈希（runner 选集）：`5c931f6a289d47b9cc42f9300a33efed785b9bb0349629807a57e6b8121e8183`。
- 实际 `main` 独立网络阻断 runner：
  `python scripts/run_creative_targeted_tests.py --root C:\Users\Reel\Documents\libtv-auto-main-sync --evidence-dir E:\Codex\cw3b-main-final --tests backend/tests/test_creative_text_contract.py`
  结果：`44 passed`，退出码 `0`；JUnit：`E:\Codex\cw3b-main-final\junit.xml`；main runner 源码哈希：
  `2f7470aee3ca3c266dd4b9e729fb7ee3df0d029b06383c103f5f8181f2e7e820`。
- 测试覆盖 v2、坏事实键/空依据、事实/锁/Reality/Prompt/Registry 变化、篡改后自算哈希、六维顺序、N/A/none、旧 Registry 与既有包形状适配。

## 发现问题

- 纯文本检查不能证明像素真值、摄影因果、自由语义修订安全或实质创意差异；报告明确保留这些边界。
- D4/E1 尚未接线，因此本模块存在不等于现有运行路径的 Preservation 漏洞已修复。

## 下一步

- PM 在 CW-3A 释放核心服务后，在 D4/E1 的持久化绑定/执行入口调用此门。建议最小接线签名：
  `validate_text_contract(plan, actual_package, frozen_package, registry_snapshot, facts_snapshot)`.
- 接线后需补服务级负断言和运行路径回归；本包不引入 Provider、模板平台、完整 DNA 提取、五维探索或自主循环。

## 同步

- testing 验证后仅将这三个白名单文件局部同步至实际 `main` 目录并独立复验。
- 三个文件均为实际 `main` 原先缺失的新文件；同步后逐文件 SHA-256 一致，main 既有差异保留。
- 本报告不宣称 `FUNCTIONALLY_VERIFIED`、`INTEGRATION_VERIFIED` 或 `PRODUCTION_READY`。
