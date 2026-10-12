# Controlled Real Production Bridge: Entry Review

日期：2026-10-12
用户指令：进入 Controlled Real Production Bridge。
状态：阶段准入核查已完成；实现范围待确认，真实提交仍未开放。

## 完成

- 接受进入新阶段的指令，核查实际 testing/main 工作目录，而非仅使用上轮隔离集成树。
- 读取产品、设计、开发计划、QA、变更记录、技术基线、ACTIVE_WORK 和 MVP-7A/7B 报告。
- 复验持久票据、输入租约、executor 与禁止 live 调用边界；没有加载真实环境配置或访问 Provider。
- 保留此前“不改 API Contract / Task State / Billing / quota / ledger”的限制；进入阶段本身没有给出这些边界的具体变更范围或某次付费请求参数。

## 当前真实实现

| 文件 | 当前行为 | 对受控实产的影响 |
| --- | --- | --- |
| backend/src/libtv_agent/api/creative_workflow.py:22 | offline_only 仅允许 test、fake/replay、local object store，禁止 paid generation | 现有导演 API 不能通过修改前端标志直接成为真实入口 |
| backend/src/libtv_agent/services/creative_image_workflow_orchestrator.py:218 | 检查 feature/admin/human、环境、approval/quote、付费及暂停门禁 | 这些检查必须保留，不能以阶段确认替代请求级证据 |
| backend/src/libtv_agent/services/creative_image_workflow_orchestrator.py:470 | live 路径固定拒绝 LIVE_EXECUTION_DISABLED_MVP7A | 不得仅删除此行就称为受控桥接完成 |
| backend/src/libtv_agent/services/creative_provider_executor.py:53 | 已有图片 adapter 协议，作用域为 FIRST_FRAME/image_edit | 优先复用现有 adapter；不新建 Provider 或第二套媒体执行器 |
| backend/src/libtv_agent/services/creative_provider_executor.py | 不创建旧图片 batch、attempt、quota reservation、ledger 或 deliverable | 仍缺已证明的端到端旧生产入口接线、费用原子边界及输出回收 |
| backend/src/libtv_agent/services/creative_provider_preflight.py:91 | 人工授权绑定 owner/task/package/shot/provider/model/request/evidence hashes、期限、币种及上限 | 当前没有本轮真实样本的这些值，不能伪造确认 |
| backend/src/libtv_agent/services/creative_provider_preflight.py:111 | quote 显式包含费用、quota、上传费用及 submit_retries=0 | 不猜价格，不将前端 readiness score 当作报价或配额证据 |
| frontend/src/features/director-studio/productionBridge.ts | 仍为只读 preparation，providerSubmissionAllowed=false | 不把规划对象升级成生产授权，不批量翻转 offline 资格 |

这些后端准备模块包含其他窗口的未提交工作；本窗口只读取和测试，没有提交、推广或修改它们。

## 首个实施包提案

提案范围为单商品、单 FIRST_FRAME、一次初始图片提交；不含视频、SHOT_01 实产、多镜、自动真实性修订或批量生产。
这是待确认的实施范围，不是已经批准的生成次数或费用授权。

1. CRB-1：确认独占文件白名单，以及允许新增/适配的受控后端入口。旧 Creative Workflow API 保持 offline-only；不得静默扩大旧 API 语义。若需要新 API/schema，先明确合同变更范围。
2. CRB-2：服务端从不可变 Production Package 拉取 Prompt 与真实许可来源，绑定现有请求级 approval、quote、持久 ticket/lease；授权不接受前端布尔值覆盖。
3. CRB-3：复用既有生产服务、adapter、幂等及账本真源，补齐提交领取/预算预占/结果持久化之间的事务与恢复证据。禁止重复扣费、第二套账本或绕过旧入口门禁。
4. CRB-4：先通过隔离替身测试：重复点击、并发领取、超时/UNKNOWN、停止、授权过期、来源撤回、包版本变化、结果落库失败和进程恢复；失败保持原严格断言。
5. CRB-5：绑定具体环境、商品/项目/包、Provider/model、输出规格、调用上限、币种/总预算和授权有效期后，执行单样本真实验证。UNKNOWN 只查询/对账，不自动重投。
6. CRB-6：回收真实输出并验证来源哈希、审核状态及恢复链；人工审核和交付继续分开。Fake/Replay 不能成为真实生产资格。

本窗口此前负责前端架构，后端核心文件归其他窗口所有。实施前需明确独占接线范围；当前未跨窗口发消息或改动共享接线文件。

## 待人工明确

- 是否允许下一实施包扩展到受控后端入口与既有生产服务接线，以及相应 API 合同边界；仍不允许重写 Task State、计费/配额/账本语义。
- 首轮真实执行的 Provider/model、真实商品或项目与 package、目标环境、最多调用次数、费用上限/币种及有效期。可以在开发包通过后提供，未提供前只运行隔离替身。
- 涉及部署、服务重启或生产迁移时单独确认；源码同步不代替这些授权。

## 测试

两侧均通过既有网络隔离 runner 执行：

```text
backend/tests/test_creative_image_workflow_orchestrator.py
backend/tests/test_creative_provider_executor.py
```

- testing：15 passed；证据 `E:/crb/t/junit.xml`。
- 实际 main：15 passed；证据 `E:/crb/m/junit.xml`。
- runner 禁止网络连接；SQLite、文件物化及替身执行均位于外部临时目录。
- 首次较长证据目录中两侧各 4 failed / 11 passed，失败位于物化目标文件路径；仅缩短外部目录后两侧 15 项全通过。未修改代码或弱化断言。原失败记录保留在 `E:/Codex/controlled-real-bridge-20261012/`。
- 本轮没有前端源码改动，未重跑 build/lint/浏览器，也不把上轮浏览器结果冒充本阶段真实链路验收。

## 修改与同步

本轮只新增此报告，在 codex/testing 提交后局部同步到实际 main；其余已提交差异、原有未提交开发和运行环境保持原状。
没有修改 API、schema、状态机、Provider adapter、生产服务、配置、数据库、密钥或 .env。

## 发现问题与下一步

阶段授权已收到，但 live 入口与执行接线仍受明确的代码硬闸和既有架构边界约束。
下一步先确认 CRB-1 的后端接线范围，再实施、隔离验证和同步源码；真实调用仅在 CRB-5 的请求级授权齐备后执行。
当前不能声明 REAL_PRODUCTION_READY 或生产闭环已完成。
