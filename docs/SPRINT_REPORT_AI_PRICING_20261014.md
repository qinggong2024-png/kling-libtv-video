# Sprint Report：AI 共享价格额度

日期：2026-10-14
范围：共享美元额度、版本化本地价格目录，以及文本、图片、视频提交边界的结算闭环。

## 完成

- 每用户每日默认 `$50`，内部整数单位为 50,000，1 单位等于 `$0.001`。
- 增加每次 `$5` 和每批 `$10` 上限；文本、图片、视频使用同一个预占池。
- 价格目录按 Provider、model、unit、effective_at、source 和 version 保存，
  生成请求时写入价格快照，支持 input/output token、图片数量和视频秒数。
- 未知价格可配置为保守上限或拒绝；不发送实时报价请求，不把 WaveSpeed
  参考价格自动用于其他 Provider。
- 结算支持实际 token、整数微美元和 provider response id。已知价格释放
  预占差额；价格或提交结果未知时保留 `UNKNOWN`。
- 同键请求按 task 作用域隔离，预占和结算使用条件更新避免重复结算；上海业务日
  从带时区 UTC 时间转换计算。
- 新增只读 API：
  - `GET /api/v1/ai-usage/quota`
  - `GET /api/v1/ai-usage/prices`
- 图片批次在真实提交前按展开 item 预占并加最后提交门；视频确认/固定任务在
  Provider 提交前按 attempt 预占并加最后提交门。提交成功按供应商 usage receipt
  结算，可靠失败释放，超时或接受状态不明保留 `UNKNOWN`。
- Fake/Replay 只允许实际 synthetic adapter 进入离线额度路径，结算为零并标记
  `OFFLINE`；没有价格快照的历史图片/视频只可查询和恢复。

## 修改

- `backend/src/libtv_agent/config.py`
- `backend/src/libtv_agent/services/ai_pricing.py`
- `backend/src/libtv_agent/services/ai_usage.py`
- `backend/src/libtv_agent/adapters/openai_analysis.py`
- `backend/src/libtv_agent/services/analysis.py`
- `backend/src/libtv_agent/services/prompt_revision.py`
- `backend/src/libtv_agent/api/tasks.py`
- `backend/src/libtv_agent/api/ai_usage.py`
- `backend/src/libtv_agent/api/router.py`
- `backend/src/libtv_agent/domain/models.py`
- `backend/alembic/versions/c9f0a1b2c3d4_ai_usage_pricing.py`
- `.env.example`
- `backend/tests/test_ai_pricing.py`
- `backend/src/libtv_agent/services/media_ai_usage.py`
- 图片生成器、视频确认/执行器及 Runner 的额度接线
- `backend/tests/test_media_ai_usage.py`
- `docs/fixtures/wavespeed-price-reference-20261014.json`
- 相关 AI usage 回归测试、CHANGELOG

## 测试

- 价格、转换、版本选择、reference-only、未知价格、请求/批次上限、共享池、
  UNKNOWN、实际用量结算、并发、重启和迁移保留：**20 passed**。
- 既有 AI usage service/workflow 回归：**11 passed**；Cutflow migration 回归另含
  15 passed、1 skipped。
- 图片/视频/创意 Provider 提交边界回归：**45 passed**。
- 分析和 Prompt Assistant 工作流：**6 passed**。
- scoped Ruff：通过。
- Alembic heads：单一 `c9f0a1b2c3d4`，parent 为 `c8e9f0a1b2c3`。

## 发现与限制

- 图片/视频正式路径已接入价格预占和最后提交门，但 `deferred_entries` 仍明确
  列出 Feedback Learning、Director planning 和 quality review；这些入口还没有
  统一计入共享池。
- 默认目录为空，因此文本 live Provider 未配置价格时按保守上限或拒绝策略处理；
  图片/视频 live Provider 必须有对应 Provider/model 的有效非 reference-only 价格。
  离线 Fake/Replay 仍以 `OFFLINE` 结算。
- 未验证 PostgreSQL 多 worker、真实供应商账单字段或正式数据库；没有真实 Provider
  调用、生产数据写入、部署或服务重启。

## 下一步

- 在独立授权下为 Feedback Learning、Director planning 和 quality review 接入同一
  价格预占/结算接口，并以真实 provider usage 或官方账单字段配置价格。
- 继续验证 PostgreSQL 锁竞争、进程崩溃恢复和管理员对账视图。
