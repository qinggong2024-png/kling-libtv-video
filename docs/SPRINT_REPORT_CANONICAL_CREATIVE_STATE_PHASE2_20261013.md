# Sprint Report: Canonical Creative State Phase 2

日期：2026-10-13  
范围：Phase 2 - Canonical Director package and storyboard read-only wiring  
状态：隔离工作树验证完成，待主 PM 在 `codex/testing` / `main` 验收；未声明已同步或 PRODUCTION_READY

## 完成

- 保持只读、内存 projection 边界，未增加 API、迁移、持久化写路径、Provider 或真实生成调用。
- 保留 Director 选定 direction、package revision、显式 `shot_id` 和 source binding。
- 当存在 `SHOT_01` 时保留根 `FIRST_FRAME`，并按显式 shot ID 装配包、选择、review 和 source。
- `FIRST_FRAME` 与 `VIDEO_STORYBOARD` 的 package、candidate、selection、review、hash 和 output mapping 独立读取。
- candidate 查找同时约束 `candidate_id`、`shot_id` 和 `package_id`；缺失或冲突时保留 unresolved/diagnostic，不借用其它 shot 的来源。
- `ShotPromptRefs` 保存已有 package revision；shot projection 保存对应 review。
- 旧 automatic/custom 输入保持只读兼容，不生成新的 shot 或虚构来源。

## 相对原始 baseline 的增量

核心功能增量集中在四个白名单文件：

- `backend/src/libtv_agent/creative/state.py`
  - 增加 shot prompt 的 `package_revision` 和独立 review 投影字段。
- `backend/src/libtv_agent/creative/state_adapters.py`
  - 保留 `FIRST_FRAME`；
  - 按显式 shot/package 约束读取 package、candidate、selection、review 和 mapping；
  - 对来源冲突抛出结构化只读冲突，避免位置借用或跨 shot 借用；
  - 保留每个 shot 的 package revision、source binding 和 review。
- `backend/src/libtv_agent/creative/state_projection.py`
  - 将适配冲突转为 projection diagnostic；
  - 对未找到匹配 candidate 的情况保留 warning 和 unresolved reference；
  - package ID 重复检查改为基于每个 shot 的实际 package 引用。
- `backend/tests/test_creative_state_phase2.py`
  - 覆盖 FIRST_FRAME / VIDEO_STORYBOARD 独立选择、审核、package revision、hash、显式 shot/package candidate binding、冲突诊断、顺序变化和旧模式兼容。

已有 foundation 测试仅同步调整了 shot order 断言，使其反映 Phase 2 明确保留 `FIRST_FRAME` 的契约。

## 修改

- `backend/src/libtv_agent/creative/state.py`
- `backend/src/libtv_agent/creative/state_adapters.py`
- `backend/src/libtv_agent/creative/state_projection.py`
- `backend/tests/test_creative_state_foundation.py`
- `backend/tests/test_creative_state_phase2.py`
- `docs/SPRINT_REPORT_CANONICAL_CREATIVE_STATE_PHASE2_20261013.md`

未修改 `state_revision.py`、`__init__.py`、`CHANGELOG.md`、`ACTIVE_WORK.md`、API、数据库、Provider、frontend 或真实 `.env`。

## 测试

使用解释器 `E:\Projects\libtv自动化生成\.venv\Scripts\python.exe`，工作目录为隔离工作树，`PYTHONPATH` 指向隔离目录 `backend\src`。

- Phase 1 foundation + Phase 2 专项：
  - `python -m pytest backend/tests/test_creative_state_foundation.py backend/tests/test_creative_state_phase2.py -q -p no:cacheprovider --capture=no`
  - 结果：32 passed；其中 Phase 2 专项按 PM 复验为 24 passed。
- scoped Ruff：
  - `python -m ruff check --no-cache backend/src/libtv_agent/creative/state.py backend/src/libtv_agent/creative/state_adapters.py backend/src/libtv_agent/creative/state_projection.py backend/tests/test_creative_state_foundation.py backend/tests/test_creative_state_phase2.py`
  - 结果：passed。
- Python compile：
  - `python -m compileall -q backend/src/libtv_agent/creative/state.py backend/src/libtv_agent/creative/state_adapters.py backend/src/libtv_agent/creative/state_projection.py backend/tests/test_creative_state_foundation.py backend/tests/test_creative_state_phase2.py`
  - 结果：passed。
- whitespace：
  - `git diff --check`
  - 结果：passed；新增 Phase 2 测试未发现 trailing whitespace。

## 发现问题

- 既有 `backend/tests/test_creative_workflow_storyboard.py` 的本地运行在 pytest fixture 初始化阶段受运行器临时目录权限阻塞：`FileNotFoundError: No usable temporary directory`。该失败发生在测试 setup，未进入业务断言；Phase 2 专项、Ruff 和 compileall 已通过 PM 复验。
- 未证明真实 PostgreSQL、Provider、持久化写路径、API 路由、frontend、生产数据和服务重启行为。
- 本 patch 只提供只读 projection 和内存诊断，不声明 migration、production synchronization、PRODUCTION_READY 或 paid generation readiness。

## 下一步

- 由主 PM 使用新鲜 baseline 比对四文件核心增量及 foundation 断言调整。
- 在 `codex/testing` 和 `main` 分别完成主分支要求的验收与 scoped promotion；本隔离工作树不执行同步。
