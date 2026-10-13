# 当前并行工作协调表

更新时间：2026-10-12

这个文件用于协调多个 Codex 对话在同一项目上的工作。每个对话开始修改代码前，先读取本文件，并在交接或完成后更新自己的状态。

## 当前总规则

- 测试分支：`codex/testing`
- 生产分支：`main`
- 所有改动先在 `codex/testing` 完成验证，再由一个明确指定的窗口局部同步到实际生产目录的 `main`。
- 不同步 `.env`、密钥、缓存、运行时状态、构建产物和临时压缩包。
- 不允许两个窗口同时修改同一个核心文件。
- 迁移、OpenAPI、共享类型和 Sprint Report 由负责该功能的窗口统一维护。
- 源码同步不代表部署、生产数据写入、迁移执行、服务重启或真实付费调用。
- 2026-10-10 CW-3 使用逐包独占白名单；每包唯一实施窗口负责自己的增量同步，PM 统一处理共享接线与最终验收。详见 `CREATIVE_WORKFLOW_PARALLEL_CW3_20261010.md`。

## 当前对话分工

### 后端：Creative Workflow

- 对话：`codex://threads/01a123cc-2aae-7562-a206-7a39d999a985`
- 派生实施窗口：`codex://threads/01a124b7-f398-77b0-bed8-185e222ef0b4`
- 状态：CW-1 至 CW-4 已完成阶段性验收；MVP-1A 至 MVP-1F、MVP-2A、MVP-2B、MVP-2C、MVP-3A、MVP-3B、MVP-4A、MVP-4B、MVP-5A、MVP-5B、MVP-6A、MVP-7A、MVP-7B 和迁移完整性修复包已完成并同步实际 main。当前已具备图片单样本的 durable ticket→input lease→executor 编排、真实性循环决策编排和历史迁移完整性修复，仍不能将 Fake/Replay 结果视为可交付。
- 负责范围：
  - Creative Workflow 后端模型、服务和 API
  - ProductVersion 事实锁
  - 授权包版本绑定、幂等和撤回审计
  - Grounded DNA、Prompt Registry、Fake 媒体映射
  - 后端迁移、后端测试、相关合同和 Sprint Report
- 当前文件归属以 `CREATIVE_WORKFLOW_PARALLEL_CW3_20261010.md` 的四包白名单为准；CW-3A 独占导演服务/API，CW-3B 只新增纯函数文字模块，CW-3C 独占旧图片审核/上传/刷新入口，CW-3D 只新增迁移测试和定向入口。
- PM 独占协调表与调度报告；实施窗口不写共享协调文档，只更新自己的报告。
- CW-3A：`01a12506-f17c-7bc2-8da0-b75eee6c6208`；CW-3B：`01a12506-f727-7e53-a563-54303c369ca2`。
- CW-3C：`01a12506-fd44-71f1-bf9a-0bbcb708c5b4`；CW-3D：`01a12507-040c-70c2-a642-050b57db634a`。
- CW-3C 第二轮修复已通过 PM 独立验收并释放白名单：两侧各 5 项聚焦、22 项旧图片/审核权限回归和 scoped Ruff 通过；保留无来源 header、Replay、导演审核统一接线等未证明边界。CW-3D 入口尚未验收，不作为公共已交付工具使用。
- CW-3B 模块已通过 PM 独立验收并释放白名单；其原先未接线缺口已由 CW-4A 补齐，D4/E1 运行接线通过独立验收。
- CW-3A 已通过 PM 独立验收并释放白名单：两侧各 28 项 Creative/Product 回归和 scoped Ruff 通过；预算、停止、创建重放和事实版本修复有效，PG/跨进程崩溃仍未证明。
- CW-3D 已完成验证但未通过整体验收：两侧各 2 项通过、2 项严格失败，确认 `product_version` 删除保护和 `creative_command` 不可变触发器缺失；CW-3E 将以新迁移修复，不回改历史迁移。
- CW-3E：`01a12738-81d4-7592-9df5-e8039ee91de7`，独占新增迁移、迁移修复测试和报告；不得修改 CW-3D 验证文件或历史迁移。
- CW-3E 已由 PM 独立复验通过：testing/main 各自 Ruff 通过、`test_creative_migration_repair.py` 3 项通过；新增 `d2f3a4b5c607` 两侧一致。CW-3D 原失败证据保留。
- CW-4 已拆成三个独占小包，调度见 `docs/CREATIVE_WORKFLOW_PARALLEL_CW4_20261011.md`：
  - CW-4A：D4/E1 文字完整性运行接线，窗口 `01a12741-eb67-7273-9a50-c727626d9c8f`；
  - CW-4B：有界自主真实性循环纯策略，窗口 `01a12741-ed12-7f23-9eb9-13a2dd404aca`；
  - CW-4C：事务、UNKNOWN、停止与进程重建恢复严格测试，窗口 `01a12741-ee82-78e0-a7ee-85914c8e0416`。
- CW-4A 通过前，不宣称现有 Preservation 漏洞已修复；CW-4B 通过前，不宣称项目已接入自主循环；CW-4C 失败时保留严格失败证据。
- CW-4 已完成 PM 独立验收：CW-4A 两侧各 75 项、CW-4B 两侧各 25 项、CW-4C 两侧各 5 项及 scoped Ruff 均通过；验收和限制见 `docs/SPRINT_REPORT_CREATIVE_WORKFLOW_CW4_DISPATCH_20261011.md`。
- CW-4A 已释放 D4/E1 文字合同运行接线；CW-4B 仅释放未接入服务的纯策略；CW-4C 仅释放隔离 SQLite 恢复证据。
- 后续风险：stop 不单独追加 `CreativeRecord` 事件；PostgreSQL、多 worker 崩溃窗口、真实账本事务边界和真实 Provider/像素质量仍未证明，需另立小包。
- 2026-10-11 已确认内部 MVP 策略：功能范围继续按任务书完成，只简化 5–10 人局域网阶段的工程验证门槛；详见 `docs/INTERNAL_MVP_DELIVERY_PROFILE_20261011.md`。
- 下一阶段优先级：stop 审计缺口、内部 MVP 一键就绪检查、导演规划接入现有图片入口；不先建设微服务、复杂 Agent 集群或高并发证明。
- MVP-1A stop 审计事件已完成并通过两侧 `2 passed`；MVP-1B 只读就绪检查已新增，异常端口测试按预期返回非零。
- 已完成的 MVP 导演闭环：
  - Director Studio 已支持正面图 → 方向选择 → 生产包 → 授权 → 离线 Fake 首帧 → 人工审核/选择；
  - 服务端审核理由可持久化并在刷新后回显；
  - 单镜 `SHOT_01` 已支持首帧选择 → storyboard 授权 → Fake 分镜 → 分镜审核/选择与素材映射；
  - 首帧与分镜审核、候选、选择分开保存，旧 `FIRST_FRAME` 合同保持兼容。
- 当前继续禁止直接扩大：
  - 将 Fake/Replay 结果送入正式图片或视频生产；
  - 未经授权调用真实 Provider、付费生成、生产数据写入、迁移或部署；
  - 直接宣称 `director_fixed` 视频已完成；
  - 多镜 storyboard、通用 Agent 集群或高并发基础设施。
- 下一阶段优先级：
  1. 真实图片 Provider 适配与 CreativeTask 到现有图片入口的独立桥接；
  2. 固定视频执行合同：服务端拉取已审核首帧/分镜，不重复上传；
  3. 在真实 Provider 接入后，再接默认关闭且预算/次数有界的自主真实性循环；
  4. 最后补多镜扩展、真实像素质量收益和生产环境专项验证。
- 当前阶段进度判断（2026-10-12，按任务书功能面而非代码行数估算）：
  - 任务书合同、隔离 Fake 闭环和来源/审核/恢复边界：约 80% 已具备；
  - 可操作的真实图片/视频生产链：约 40%；
  - 真实 Provider、像素复核和自主循环运行接线：约 20%；
  - 综合开发完成度约 75%–80%。这是研发进度估算，不是上线就绪度。

### 前端：Creative OS 架构

- 对话：`codex://threads/01a124b1-a8dd-7fc1-a7cf-64cf3bd1c32e`
- 状态：正在按该窗口用户指令补 Milestone 0.1 隔离运行验证；本轮不接管其启动端口、浏览器依赖或前端文件。
- 负责范围：
  - Creative Project 类型、上下文和 adapter 设计
  - 后端 API 稳定前的 mock 与接口接入准备
  - Director Studio 的前端信息架构草案
  - 保持 `ImageCenter`、`ProductionWorkspace`、现有深链接和轮询行为兼容
- 当前禁止扩展：
  - 不修改后端模型、迁移或后端 API
  - 不大规模重命名或删除 `ImageCenter`
  - 不把 CreativeTask 状态替换为旧任务状态
  - 不把 Fake 结果显示为正式合格或可交付结果

## 文件协调

### 后端窗口可修改

- `backend/src/libtv_agent/creative/`
- `backend/src/libtv_agent/services/creative_workflow.py`
- `backend/src/libtv_agent/api/creative_workflow.py`
- 与本包直接相关的 `backend/src/libtv_agent/domain/` 文件
- 与本包直接相关的 `backend/alembic/versions/` 文件
- `backend/tests/` 中的 Creative Workflow 测试
- Creative Workflow 合同和对应 Sprint Report

### 前端窗口可修改

- 新增的 `frontend/src/domain/creativeProject/`
- 新增的 `frontend/src/features/creative-project/`
- 新增的 mock、adapter 和前端测试
- 只有在 API 字段冻结后，才修改 `frontend/src/api.ts`

### 暂时锁定的共享文件

除非先在本文件登记并取得另一窗口的交接，否则暂不修改：

- `frontend/src/app/App.tsx`
- `frontend/src/app/useAppNavigation.ts`
- `frontend/src/api.ts`
- `backend/src/libtv_agent/domain/models.py`
- `backend/src/libtv_agent/domain/schemas.py`
- `backend/src/libtv_agent/domain/enums.py`
- `openapi.yaml`
- `docs/CHANGELOG.md`
- 已在其他窗口进行中的 Sprint Report

## 交接要求

窗口完成一个阶段后，必须记录：

1. 修改的文件和未修改的文件。
2. API、类型或状态合同的变化。
3. 测试命令和结果。
4. 是否已在 `codex/testing` 验证。
5. 是否已同步实际 `main`，以及同步范围。
6. 未解决风险和下一窗口可以继续做的事情。

## 待确认事项

- Creative Project 第一阶段是否只保存前端上下文，还是立即接入持久化项目 API。
- 后端 Creative Workflow API 的字段和错误码冻结后，前端才开始真实 adapter 接入。
- Checkpoint 1 仍需人工确认，测试通过不等于产品方向已接受。

## 最近一次状态

- 2026-10-11：MVP-1F 已完成，Director Studio 优先显示服务端 `latest_review` 决定和拒绝理由；testing/main 定向测试、build、lint、桌面/移动隔离流程通过。
- 2026-10-11：MVP-2A 已完成，单镜 `SHOT_01` storyboard 离线合同闭环通过 testing/main 各 42 项 Creative Workflow 回归及专项验证；4 个白名单文件同步成功。
- 2026-10-11：MVP-2B 已完成，Creative 首帧到现有图片入口的桥接前置计划通过 testing/main 回归，Fake 仍不可提交。
- 2026-10-11：MVP-2C 已完成，`director_fixed` 视频前置计划通过 testing/main 专项回归，旧 automatic/custom 视频行为未修改。
- 2026-10-12：以上包均未调用真实 Provider、未执行迁移/部署，Fake 结果仍为 `OFFLINE_SYNTHETIC_ONLY`，不可交付；MVP-3A 开始补 Provider 请求合同 dry-run/replay。
- 2026-10-12：MVP-3A 已完成，图片和 `director_fixed` 视频请求合同支持 dry-run/replay，锁定 Prompt、角色顺序、对象哈希和幂等键可恢复复验；testing/main 独立回归通过。
- 2026-10-12：MVP-3B 已完成，补齐素材临时物化、能力声明、许可、预算和人工 Provider 授权预检；testing/main 组合回归通过，仍未执行 Provider POST。
- 2026-10-12：MVP-4A 已完成，新增不可变 ProviderSubmissionTicket、进程内幂等领取和 SUBMITTED/UNKNOWN/FAILED 对账合同；testing/main 各 303 项组合回归通过。UNKNOWN 禁止自动重提，FAILED 必须使用新幂等键；未调用 Provider、未扣费、未写 quota/ledger/attempt。下一步补持久化票据与单机原子领取边界。
- 2026-10-12：MVP-4B 已完成，新增持久化 provider submission ticket、唯一幂等键和事务性 claim；testing/main 独立组合回归各 214 项，专项与 MVP-4A 各 27 项通过。仍未调用 Provider、扣费或执行生产迁移；下一步进入默认关闭、人工授权、单样本的真实图片 Provider 接线。
- 2026-10-12：MVP-5A 已完成，补齐图片 `FIRST_FRAME/image_edit` executor 边界；dry-run/replay 不调用 Provider，live 需要管理员开关、人工确认和既有付费控制，testing/main 专项通过。
- 2026-10-12：MVP-5B 已完成，补齐 durable input lease/materialization、对象哈希、权限/许可校验和租约状态；testing/main 专项各 5 项，组合各 263 项通过。已知两个历史迁移触发器测试失败与本包无关，待独立修复。
- 2026-10-12：MVP-6A 已完成，补齐按 Product→Direction→DNA_REALITY→TEXT_PACKAGE→AUTHORIZATION→E1→CRITIC→TARGETED_REVISION 顺序执行的真实性循环运行门；testing/main 各 49 项回归通过，仍未接入实际 worker 或 Provider。
- 2026-10-12：迁移完整性修复包已完成，保留历史 migration 不变，以后续 migration 修复 product_version 删除保护和 creative_command 不可变触发器；testing/main 各 7 项通过，未执行生产迁移。
- 2026-10-12：MVP-7B 已完成，将 MVP-6A 运行门接入独立 Creative 编排器；testing/main 各 34 项通过，只输出下一阶段命令、revision 摘要和审计事件，不调用模型/Provider。
- 2026-10-12：MVP-7A 已完成，将 durable ticket、durable input lease 和图片 executor 串成单样本编排边界；testing/main 相关组合回归通过，专项 8 项通过。dry-run/replay/test-double 可复验，live 在 MVP-7A 安全闸停止，未调用 Provider、未扣费或写生产数据。
- 2026-10-12：MVP-2D 已完成，Director 任务引用持久化、GET 恢复、失效清理和网络失败保留通过 testing/main 回归；浏览器 File 不作为真源。
- 2026-10-12：MVP-2E 已完成，Director 结果接入 Video Studio 的只读 `director_fixed` 离线准备区，显示 package/shot/candidate/hash/mapping；旧 automatic/custom 保持不变。补齐 Canonical Product、背面假设、Grounded Claims、Reality 六维和 Prompt/Preservation 证据展示。
- 2026-10-12：MVP-2E testing 44 个测试文件/279 项通过，main 47 个测试文件/282 项通过；两侧 lint/build 通过。尚未执行真实 Provider、正式版浏览器验收或部署。
- 当前决策门：真实图片 Provider 单样本执行需要业务确认 SKU/素材许可、Provider/model、预算、管理员 live 开关和一次人工确认；在这些信息确认前不执行真实 POST。
