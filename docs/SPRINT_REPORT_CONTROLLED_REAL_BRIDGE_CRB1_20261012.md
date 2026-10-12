# Controlled Real Production Bridge: CRB-1

日期：2026-10-12
授权：用户批准受控后端入口与既有生产校验接线。
状态：CRB-1 预检入口完成；真实提交、票据接线和生产闭环未完成。

## 完成

- 新增独立 `POST /api/v1/creative-production-bridge/tasks/{task_id}/preflight`。
- 默认关闭；服务端显式配置可信策略与 task binding 后才进入校验。
- 复用既有 Creative 请求编译器及生产 preflight validator，不复制生成管线。
- 保留认证、review-write、CSRF、owner/version、来源、授权、许可、报价、额度及暂停检查。
- 返回无 Prompt、无文件路径、无 object key 的预检证据；退出时关闭临时输入租约。
- 不调用 Provider，不创建 ticket/batch/attempt，不预占或结算，不修改 task/ledger/quota。
- 旧 Creative Workflow API、offline-only 与 LIVE_EXECUTION_DISABLED_MVP7A 硬闸保持原样。

## 修改

本次源码提交白名单：

| 文件 | 修改 |
| --- | --- |
| backend/src/libtv_agent/services/controlled_image_bridge.py | 默认关闭策略、可信绑定、预检编排及精简响应 |
| backend/src/libtv_agent/api/controlled_image_bridge.py | 严格 request schema、身份/角色检查及错误转换 |
| backend/src/libtv_agent/api/router.py | 仅新增一行 import 与一行 include_router |
| backend/tests/test_controlled_image_bridge.py | 22 项隔离断言 |
| docs/contracts/controlled-image-bridge-preflight.v1.md | 新入口合同、错误码、权限与副作用边界 |

本报告为单独文档提交。没有修改共享 CHANGELOG、ACTIVE_WORK、既有
openapi.yaml、前端源码、领域模型、迁移、环境配置或生产 adapter。

实现提交：testing `d6c1708`；实际 main `519c5f4`。
实际 main 目录：`C:/Users/Reel/Documents/libtv-auto-main-sync`。
源码同步不代表部署、迁移、服务重启或付费执行。

## 测试

两侧均在禁止网络的独立进程中运行，SQLite 与文件物化使用外部临时目录：

| 验证 | testing | 实际 main |
| --- | --- | --- |
| 新入口、既有 image orchestrator、Provider executor | 37 passed | 37 passed |
| 既有 auth、image generation batches | 18 passed | 18 passed |
| 本次四个 Python 文件 scoped Ruff | passed | passed |

合计：每侧 55 passed；两侧 110 passed。

JUnit：

- testing：`E:/crb/c2t/junit.xml`、`E:/crb/r1t/junit.xml`。
- main：`E:/crb/c2m/junit.xml`、`E:/crb/r1m/junit.xml`。

新增断言覆盖默认关闭、可信绑定不可变、owner/version、拒绝客户端权限覆盖、
认证/CSRF/角色、授权撤销与过期、预算/付费门禁、重复预检、数据库计数不变、
禁止上传/提交/额度预占/结算/票据领取/执行器调用、临时路径清理及敏感信息排除。
API 成功测试只向 validator 提供独立合成设置；应用保持 Fake/禁止付费。

另在 `E:/crb/promote` 干净检出验证：可选 Creative preparation 模块缺失时，
现有总路由可导入，FastAPI OpenAPI 包含新增入口，默认策略返回 403
CONTROLLED_BRIDGE_DISABLED。没有启动服务或加载真实 .env。

首次干净检出探针直接读取路由 `.path`，因当前 FastAPI 嵌套路由对象无此字段
而失败；改为检查应用 OpenAPI 后通过。仅修正外部探针，未改生产实现。

本次无前端改动，未重跑 frontend build/lint/browser；上述结果不是浏览器、
真实 Provider、PostgreSQL 或多 worker 的验收。

## 发现问题

1. CreativeTask 及编译器/preflight 等准备模块仍包含其他窗口的未提交代码。
   CRB-1 没有将这些工作纳入提交或推广。完整成功路径目前仅在两侧实际工作树
   中验证，不能声称干净检出具备完整桥接依赖。新服务延迟加载这些模块：
   默认关闭不加载；启用后缺失依赖返回 503
   CONTROLLED_BRIDGE_DEPENDENCIES_UNAVAILABLE。
2. main 路由存在其他窗口的未提交 Creative 接线，三方合并出现两处相邻新增
   冲突。保留双方 import/mount，未覆盖生产已有 products 路由。推广工具检查
   文件指纹并保留 171 个无关脏文件路径；测试树仅暂存本次两行路由增量。
3. READY_FOR_HUMAN_SUBMIT 仅为预检证据标签。响应固定
   PREFLIGHT_ONLY、provider_submission_allowed=false、actual_submitted=false、
   OFFLINE_SYNTHETIC_ONLY、provider_capabilities_verified=false、
   deliverable_eligible=false。不代表真实生产资格或提交许可。

## 下一步

CRB-1 在此收口。下一包需要衔接不可变 package、请求级授权、持久 ticket/lease，
再处理既有生产入口、幂等、预算事务及 UNKNOWN 恢复；不得通过删除旧硬闸上线。
这些接线涉及状态与生产流程边界，尚未在本包实施。

真实验证仍需具体 Provider/model、真实来源/package、目标环境、调用上限、
币种/预算与有效期。没有这些请求级授权前，不执行真实 Provider 调用。
