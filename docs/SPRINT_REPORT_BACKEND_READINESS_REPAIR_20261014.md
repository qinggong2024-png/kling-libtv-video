# Backend Production Readiness Repair

日期：2026-10-14  
范围：Backend Workflow、API、Service、Domain State、Persistence、Execution Boundary

## 完成

- Creative Package 已成为图片和视频生产请求的服务端绑定上下文。
- 图片请求保存 workflow、package、shot、prompt hash 和 source lineage；视频变体保存来源图片、Package 和 storyboard order。
- 保留现有 WaveSpeed、Kling 和 LibTV Provider Executor，没有新增 Provider 或生成流程。
- 图片进入视频前在任务创建、Worker 执行前和 Provider submit 前重新检查 `QUALIFIED`、owner、持久化媒体和绑定 Package。
- 阻塞会写入 `phase_reason_code`、错误码和 `VIDEO_SOURCE_BLOCKED` 审计事件。
- Review queue 按技术成功且最终审批为 `PENDING` 查询，独立于首页数量、Records 筛选和父任务 phase。
- 统一暴露 `technicalSuccess`、`reviewRequired`、`deliveryState`，保留 `SUCCEEDED → REVIEW_REQUIRED → APPROVED → DELIVERABLE` 语义。
- Director 分析失败会持久化为 `ANALYSIS_FAILED`，重试沿用原 Product、Workflow 和 `client_key`，不重复创建。
- 恢复入口验证 user、Product/Workflow ownership 和 Package 绑定；幂等 replay 在 rollback 后使用标量身份值。

## 修改

- 新增 `backend/src/libtv_agent/services/creative_production_context.py`。
- 新增 `backend/src/libtv_agent/services/video_input_qualification.py`。
- 修改 Director workflow、图片批次、固定视频任务、Legacy task、Worker supervisor、状态投影和审核 API。
- 新增 `backend/tests/test_backend_readiness_repair.py`，覆盖 Package lineage、资格撤销、跨账户恢复、分析失败恢复、Review queue 和 claim fence。
- 保留 Creative State 架构、Provider adapter、数据库表结构和现有生成流程；命令合同仅增加 `retry_analysis`。

本轮完整文件清单（相对于仓库根目录）：

```text
backend/src/libtv_agent/api/creative_workflow.py
backend/src/libtv_agent/api/image_generations.py
backend/src/libtv_agent/api/tasks.py
backend/src/libtv_agent/api/video_tasks.py
backend/src/libtv_agent/creative/workflow.py
backend/src/libtv_agent/domain/schemas.py
backend/src/libtv_agent/runner/supervisor.py
backend/src/libtv_agent/services/analysis.py
backend/src/libtv_agent/services/confirmation.py
backend/src/libtv_agent/services/creative_workflow.py
backend/src/libtv_agent/services/creative_production_context.py
backend/src/libtv_agent/services/fixed_video_tasks.py
backend/src/libtv_agent/services/image_generations.py
backend/src/libtv_agent/services/state_machine.py
backend/src/libtv_agent/services/tasks.py
backend/src/libtv_agent/services/video_input_qualification.py
backend/tests/test_backend_readiness_repair.py
backend/tests/test_creative_workflow.py
docs/CHANGELOG.md
docs/SPRINT_REPORT_BACKEND_READINESS_REPAIR_20261014.md
```

## 入场判断

- 真实缺口：Package 未连接普通生产请求、视频 Worker 未重读图片资格、待审发现受父任务阶段影响、分析失败未持久化。
- 已有能力：身份隔离与共享会话门禁、任务/上传的 owner 查询、client key 的 user 作用域、技术状态与最终审批字段、现有 Provider 执行与未知提交保护。保留这些最近的修复。
- 本轮只补连接、状态投影、恢复和执行校验，不另建 Workflow/State/Adapter。
- 现有后端没有独立业务 Project 实体；恢复以 owner-scoped Product/Workflow/Task 为入口，远程 project UUID 不作为独立授权凭据。

## 数据流

```text
Director Workflow
  -> frozen Creative Package
  -> ImageGenerationBatch / Item request_json
  -> ImageGenerationOutput
  -> StagedUpload.source_image_output_id
  -> ParentTask Asset
  -> GenerationVariant.generation_config_json
  -> Worker qualification guard
  -> existing Provider Executor
  -> technical result
  -> review-required queue
  -> final approval
  -> deliverable state
```

每个绑定包含 `workflowId`、`packageId`、`shotId`、revision、source hash、package hash 和 contract hash。Provider payload 仍只携带 Provider 所需字段，生产上下文保存在持久化记录中。

## 状态变化

- 图片质量：`PENDING → QUALIFIED` 后如果变为 `REJECTED`，视频任务创建或执行会停止，并保留阻塞原因。
- 交付：技术成功只映射为 `REVIEW_REQUIRED`；人工批准后才是 `DELIVERABLE`。
- Director：`DRAFT → ANALYSIS_FAILED → AWAITING_DIRECTION`，重试使用同一任务记录。
- 创建请求仍重放原始回执；`GET /creative-workflow/recovery/{client_key}` 返回最新持久化状态。失败重试必须使用当前版本，已成功命令继续按 command key 幂等重放。
- 未绑定 Package 的 Image/Video 请求不把新增 null 字段加入哈希，兼容旧幂等记录。

## 测试

- testing：最终 readiness 15 项通过；核心 Director、状态、身份和恢复集合 240 项通过。
- main：最终 readiness 15 项通过；同步后的核心集合 240 项通过；较早 readiness/Director 子集 65 项通过。集合重叠，不把这些数字相加。
- 两侧 readiness 测试和最终全部本轮文件 Ruff 均通过。验证期间 testing 的并行 AI usage 改动曾出现 import 排序 I001，最终检查已消除；本轮没有推广该并行功能。
- 扩展旧回归在 testing 和推广前 main 均为 98 passed / 64 failed / 8 skipped；进一步 testing human review/G1 子集为 47 passed / 55 failed / 5 skipped。52 项 human review 失败源于 fixture 的 SimpleNamespace 缺少新增 `offline_authentication` 设置；其余是旧测试未配置 internal pilot/paid 门禁和既有 G1 claim/uncertain 预期差异。没有放宽生产门禁。
- 未执行浏览器验证、真实 Provider 生成、真实付费提交、PostgreSQL 多 Worker 并发和线上数据库写入。

## 发现

- Director analyzer 当前仍是规则型分析，不能证明真实视觉模型分析。
- SQLite 测试证明功能路径；PostgreSQL 行锁和多进程 Worker 仍需独立验收。
- Review queue 已有后端统一入口，但前端本轮未修改，现有页面是否展示该入口仍是剩余集成项。
- 规则型 Package 可作为受门禁约束的生产计划输入；仅去除 prompt 的历史 Fake transport 前缀，保留 planning evidence 和冻结合同。Fake 媒体仍不得 QUALIFIED 或进入真实视频，不声称规划已通过视觉分析。
- 普通 raw upload 保留既有准入语义；无法对客户端刻意去除来源关联后重新上传的字节做全库来源识别。

## 源码同步

- 本轮 20 个文件已同步到实际 main 工作目录，保留两侧原有脏改动和生产差异。
- 使用入场文件备份生成局部 patch；不同的 task 取消/恢复实现手工合并，只增加本轮校验和投影。
- 并行 visual plan、AI usage、Cutflow 等改动不纳入本轮修复清单；不以完整文件覆盖生产树。
- 没有提交/推送远程、修改真实 `.env`、生产数据、生成物，或部署/重启服务。

## 下一步

- 用隔离 PostgreSQL 和两个 Worker 复验 qualification revoke 与 claim fence。
- 用 Provider sandbox 或明确批准的 pilot 环境执行一次非付费提交合同验收。
- 前端接入 `/tasks/review-required` 和 `deliveryState`，另行进行页面验收。
- 继续保留真实 Provider、账号隔离、人工审批和交付状态门禁。
