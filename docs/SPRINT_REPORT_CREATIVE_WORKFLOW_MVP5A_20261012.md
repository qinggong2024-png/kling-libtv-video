# Sprint Report · Creative Workflow MVP-5A

日期：2026-10-12  
范围：Creative `FIRST_FRAME/image_edit` Provider executor/adapter boundary  
testing：`E:/Projects/libtv自动化生成`，`codex/testing`  
实际 main：`C:/Users/Reel/Documents/libtv-auto-main-sync`，`main`

## 完成

新增独立 `creative_provider_executor` 服务，将 MVP-4B durable
`ProviderSubmissionTicket`、MVP-3B 当前 materialized input/preflight 和现有
图片 Provider adapter 之间收口为图片单样本执行边界。

本包只支持 Creative `FIRST_FRAME` / `image_edit`。executor 在任何 adapter
调用前检查：

- ticket、request、preflight 的 owner、task、package、Provider、model、镜头、
  request/evidence/preflight hash 和稳定幂等键；
- ticket 与 preflight 的有效期、`READY_TO_SUBMIT` 状态、materialized input
  manifest、输入文件存在性和 SHA-256；
- 当前 ticket 的 durable 状态；`SUBMITTED`、`UNKNOWN`、`FAILED`、
  `INVALIDATED` 不允许同键再次执行；
- live 路径的第二次 request/preflight 复验、Provider 能力声明、人工授权、
  报价、额度、许可和既有暂停/付费控制。

执行模式合同：

- `dry-run`：只返回 `PREPARED`，不上传、不 POST；
- `replay`：只返回 `REPLAYED`，不上传、不 POST；
- `test-double`：必须显式注入带 `is_test_double=True` 的替身；
- `live`：默认关闭，必须同时具备管理员开关、人工确认、非 test 环境和既有
  付费/Provider 控制；本轮测试没有进入此路径。

结果明确返回 `actual_submitted`、`qualification_scope` 和
`deliverable_eligible`。dry-run、replay 和 test-double 固定为
`OFFLINE_SYNTHETIC_ONLY`、不可交付；真实 Provider 提交也只标记为
`REAL_PROVIDER_SUBMITTED_UNQUALIFIED`，不会自动变成人工合格或交付。

## 修改

新增白名单文件：

- `backend/src/libtv_agent/services/creative_provider_executor.py`
- `backend/tests/test_creative_provider_executor.py`
- `docs/SPRINT_REPORT_CREATIVE_WORKFLOW_MVP5A_20261012.md`

没有新增或修改 durable input lease/materialization 服务、API、OpenAPI、
共享 domain/models、旧 `image_generations` 服务、旧批次/配额/attempt/账本、
Provider adapter、前端或 `.env`。

## 测试

testing：

- MVP-5A 专项：`7 passed`；
- MVP-3A/3B、MVP-4A/4B、creative image/video bridge、storyboard、旧 image
  generation batch、quota 和 submission race 组合回归通过；
- scoped Ruff：通过；
- `git diff --check`：通过。

专项覆盖 dry-run/replay 零 adapter 调用、live 默认双门禁、test 环境硬阻断、
显式 test-double、终态 ticket 拒绝、过期 ticket 拒绝，以及输出资格字段。

## 发现问题

- 当前 executor 使用 MVP-3B 短生命周期 materialization lease。真实提交服务
  仍需要由独立包提供 durable input lease 或等价的提交期物化方案；本包不实现。
- 本包没有执行 Provider POST、上传、配额预占、费用扣除、ledger/attempt 写入、
  真实像素复核、人工 QUALIFIED 或交付。
- PostgreSQL 多 worker、进程崩溃窗口、真实费用原子化和线上配置仍未证明。

## 下一步

真实单样本图片验证前，需要人工批准：

1. 具备使用许可的单个 SKU、Canonical Product 原图和 Provider 输入许可；
2. 明确 Provider、model、报价币种、单样本预算和最大调用次数；
3. 管理员在独立配置中开启真实图片 Provider；
4. 业务负责人对本次 `FIRST_FRAME` 生成进行一次明确人工确认；
5. 由后续窗口提供 durable input lease/物化、真实费用原子化、提交后
   UNKNOWN 对账和真实输出审核方案。

本轮没有真实 Provider POST，没有费用，没有生产数据写入，没有生产迁移、
部署或服务重启。

## 同步

testing 验证通过后，只同步上述三个白名单文件到实际 `main`，保留 main
生产专属差异、未提交改动、密钥、`.env`、缓存、运行时状态和构建产物。
同步后在实际 main 独立复验 MVP-5A 专项、组合回归、scoped Ruff 和
`git diff --check`，并核对三份白名单文件 SHA-256 一致。
