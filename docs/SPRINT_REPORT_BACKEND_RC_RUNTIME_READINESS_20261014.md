# Backend RC Runtime Readiness Report

日期：2026-10-14。
结论：**RC Runtime 已形成，可进行下一步真实样本前置准备；真实生成仍保持关闭。**

## A. Runtime Identity

RC 使用从 actual `main` 工作目录冻结的源码快照，基础提交为：

`c6ef237af0a3a41a977a1fc4a5d821182d597864`

源码快照指纹：

`10485925bc25a478d4dd6dae965b814095d99430240aa3b103deca8937eb81e3`

运行时启动方式：

- API：独立隐藏进程，`launch_rc.py` → `libtv_agent.app:create_app` → Uvicorn。
- Worker：独立隐藏进程，`launch_rc.py worker` → `libtv_agent.runner.service_runtime:run_service_loop`。
- RC API：`http://127.0.0.1:8012`。
- 原有 8000 API 保留为 Windows Service `LibTVProductionApi`，仍是 query-only 维护服务，未替换。
- RC 使用独立数据目录、cookie 名称、对象存储前缀和加密 Provider 配置副本。
- RC 配置文件已生成 SHA256 manifest，启动时校验配置未被修改。

RC `/api/v1/system/status` 返回：

- `sourceRevision`：与冻结快照一致。
- `schemaRevision`：`ca01b2c3d406`。
- `configRevision`：`e24e3d23fae71063ad3e0710ffea197dfe85576f210f93fca2153b8490c3b8fa`。
- `sharedAuthentication`：`true`。
- maintenance header：不存在。

## B. Database And Runtime Mode

隔离数据库：

`postgresql+asyncpg://g1_acceptance@127.0.0.1:15439/g1_safety`

验证结果：

- Alembic current head：`ca01b2c3d406`。
- Expected head：`ca01b2c3d406`。
- Missing tables：空。
- RC `/api/v1/health/ready`：HTTP 200。
- Worker：`ONLINE`，心跳正常。
- `globalPaused=true`。
- `paidSubmissionsPaused=true`。
- generation command、Provider submission ticket、AI usage reservation：均为 0。
- 没有残留 `acceptance_*` 或 `test_*` schema。

正常 Workflow 写入探针通过：

- 登录：HTTP 200。
- Product 创建：HTTP 201。
- Director Workflow 创建：HTTP 201。
- `analyze`：HTTP 200。
- `select_direction`：HTTP 200。
- 使用同一 `client_key` 重放：返回同一 Workflow。
- recovery 查询：返回同一 Workflow。
- 本次合成探针 Product：`ea45b9e8-fb72-40ec-a5fc-5200c08bad08`。
- 本次合成探针 Workflow：`d61683fd-273e-48fa-ae9d-7be1a8dd356e`。
- Package：`d61683fd-273e-48fa-ae9d-7be1a8dd356e:package:1`。

探针只验证 RC 可写和幂等恢复，没有创建 Image Request、Video Request，也没有调用 Provider。

## C. Director Mode

RC 使用：

- `directorWorkflowMode=live_director`
- `aiAdapterMode=fake`

这表示 RC 开放正常 Director Workflow endpoint，使用真实的 Workflow、Package、持久化和恢复边界。当前 `analyze` 路径由仓库内确定性 Director 分析逻辑生成，不代表已调用 OpenAI 或其他 LLM。真实样本测试若需要真实 LLM 分析，仍需单独启用并验证真实分析适配器和价格预算。

RC 没有使用 `offline_demo`，也没有用 offline demo 绕过正常写入边界。

## D. Kling Readiness

当前 Provider：

- provider：`kling_official_api`
- model：`kling-3.0-omni`
- API endpoint：官方北京 endpoint

验证结果：

- Authentication：Passed。
- Official read-only task query：Passed。
- Adapter status：`KLING_API_READY`。
- `authenticated=true`、`available=true`。
- Query returned task count：0。
- Provider submit calls：0。
- Local Provider contract sandbox：28 tests passed。
- Official generation sandbox：**未验证**。当前 Provider capability 没有声明独立 sandbox target；按要求没有发送生成请求。

本次只验证了官方只读查询和本地 request/adapter/contract 测试，没有创建 Provider task、消耗额度或提交真实媒体。

## E. Blocking Items

RC Runtime 本身不再被以下项目阻塞：

- 源码身份：Passed。
- PostgreSQL migration/readiness：Passed。
- 非 maintenance query-only：Passed。
- 正常 Product/Workflow 写入：Passed。
- Workflow 幂等恢复：Passed。
- Worker 启动和心跳：Passed。
- Kling authentication/query capability：Passed。

真实样本执行前仍有边界：

1. Runtime Control 当前暂停所有生成，必须由授权方在真实样本窗口前明确解除暂停。
2. 当前 RC 使用 `aiAdapter=fake`，只证明 Director workflow contract；真实 LLM analysis 尚未验证。
3. Kling 官方生成 sandbox 未提供或未验证；真实 Provider 生成只能作为受控生产操作单独批准。
4. RC 源码是带工作区未提交变更的冻结快照，虽有 source fingerprint，但尚不是不可变 Git release commit。
5. 本轮使用了隔离数据库中的合成 Product/Workflow 写入探针；它们不是用户真实商品，也不是生产样本验收记录。

## F. Pre-conditions Before Real Sample

- 指定真实商品、源素材、测试账户和 owner。
- 确认 RC source fingerprint、database head、config revision 不变。
- 通过人工授权明确生成窗口、Provider、时长、预算和停止条件。
- 决定 Director 使用确定性分析还是启用真实分析适配器，并准备对应价格合同。
- 保持单商品、单 Image Request、单 Video Request。
- 在 Image 进入 Video 前完成真实人工 `QUALIFIED` 审核。
- 保存每一步的 request ID、Product/Workflow/Package/shot、Image output、Video attempt、Provider task、Review 和 Delivery 关联。
- 生成窗口结束后恢复 `globalPaused=true` 和 `paidSubmissionsPaused=true`，并重新执行 readiness 与 runtime identity 检查。

本轮没有真实生成、批量生产、Provider submit、数据库结构修改、业务代码修改或 Workflow/state machine 修改。
