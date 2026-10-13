# Sprint 6 Report：Backend Runtime Stability Audit

日期：2026-10-13
分支：`codex/testing`
范围：验证 Creative OS 核心到人工审核的后端运行链稳定性，不新增业务能力

## 完成

Sprint 6 的离线运行稳定性验收已完成。已验证的链路为：

```text
Product
→ Brand DNA
→ Creative Package
→ Image Adapter
→ Video Adapter
→ Human Review
```

本轮保持以下边界：

- 未调用真实 Provider；
- 未产生付费请求；
- 未执行数据库迁移；
- 未修改数据库架构；
- 未新增 Agent；
- 未修改 offline safety boundary；
- 未执行批量、自动循环或生产部署。

## 当前运行链路

1. Product 输入以产品版本、对象键和资产哈希进入 Creative Package。
2. Brand DNA 以 profile ID、版本和内容快照绑定到 Package。
3. Creative Package 作为冻结输入编译为现有 image-generation-batches 输入。
4. 合格图片输出以 source image hash、output hash、shot ID、package lineage 和
   revision lineage 接入现有 video task 输入。
5. Human Review 记录 PASS/FAIL 结果、原因码、输入输出哈希、Package 版本和 prompt
   快照关联。
6. 失败恢复在不重复提交、不漂移 lineage 的前提下恢复到可重试状态。

## API 状态

| Endpoint | 状态 | 验证结果 |
| --- | --- | --- |
| `GET /api/v1/health/live` | 可用 | 不依赖数据库、schema 或 Provider，返回 200 |
| `GET /api/v1/health/ready` | 可用 | 只读检查数据库和 schema；正常返回 200，异常稳定返回 503 |
| `POST /api/v1/health/live` | 按契约拒绝 | 返回 405 |
| `POST /api/v1/health/ready` | 按契约拒绝 | 返回 405 |
| Creative Workflow 合同 | 通过离线测试 | 状态、文本契约、记账和恢复场景通过 |
| Image Adapter | 通过离线测试 | 输入校验、快照和安全边界通过 |
| Video Adapter | 通过离线测试 | 合格图片输入、镜头和 lineage 通过 |
| Human Review | 通过离线测试 | PASS/FAIL 及原因码记录通过 |

## 已验证接口与不变量

本轮专项测试持续验证以下字段：

- `creativeStateRevision`
- `packageId`
- `productAssetHash`
- `promptSnapshot`
- Brand DNA profile ID 和 version
- image output hash
- `shotId`
- package lineage
- revision lineage
- Human Review 的输入哈希、输出哈希和 prompt hash

Health readiness 只执行只读数据库检查，不执行 Alembic migration、Provider
availability probe、credential verification 或付费调用。

失败恢复已验证：

- UNKNOWN 状态可进入 reconciliation；
- reconciliation 幂等，不重复提交；
- 人工审核门保持有效；
- revision、asset hash、prompt snapshot 和 Brand DNA version 不漂移；
- Fake/offline 输入在 adapter 边界被阻断；
- 失败后可重试并恢复，不产生付费副作用。

## 测试结果

testing 分支组合回归共收集并通过 107 项：

```text
backend/tests/test_health.py                                      7
backend/tests/test_runtime_workflow_integration.py                5
backend/tests/test_runtime_stability_recovery.py                  4
backend/tests/test_creative_workflow_recovery_contract.py         5
backend/tests/test_creative_workflow_accounting.py                5
backend/tests/test_workflow_integration.py                       33
backend/tests/test_creative_workflow.py                           21
backend/tests/test_creative_workflow_text_contract_integration.py  6
backend/tests/test_submission_recovery.py                         5
backend/tests/test_launch_started_recovery.py                    14
backend/tests/test_g1_confirmation_recovery.py                    2
```

Ruff：

```text
All checks passed
```

`git diff --check`：通过。

## 未验证部分

- 未连接真实 PostgreSQL、真实生产 schema 或正式服务；
- 未在正式入口 `http://192.168.30.126:5173/` 执行真实业务链；
- 未执行真实 Product 样本；
- 未生成真实图片或视频；
- 未调用真实 Provider，也未验证真实 Provider 返回、超时和供应商侧状态；
- 未验证真实图片像素质量、视频运动质量、服装一致性和人工业务效果；
- 未执行批量任务、多 worker、灾备或生产部署验证。

## 真实样本测试前剩余风险

工程合同和离线运行链已通过，但真实样本仍可能暴露：

- 真实产品资产格式、尺寸、权限或对象存储路径与 fixture 不一致；
- 真实 Provider 对 prompt、参考图、模型参数或视频输入的约束差异；
- 真实图片输出的 hash、对象存储回写和视频首帧交接差异；
- 人工审核人员对人物、服装、空间、光线、运动和镜头的业务判定差异；
- 正式运行环境的 PostgreSQL schema、配置版本、网络和凭证问题。

因此 Sprint 6 完成表示后端工程链达到单样本人工测试准备状态，不表示上线、
生产部署或付费生产批准。

## testing/main 同步

主报告创建后，将只同步本 Sprint 白名单文件到实际生产工作树
`C:\Users\Reel\Documents\libtv-auto-main-sync` 的 `main` 分支，并在 main
独立运行同一组测试、Ruff 和 diff 检查。同步结果将在本节更新；未同步用户未跟踪
ZIP、缓存、运行时状态、真实 `.env` 或生成产物。

## 下一步

等待用户明确批准后，执行一个产品、一个图片任务、一个视频任务的真实样本测试。
在批准前不调用真实 Provider、不产生付费请求、不写入生产数据、不部署服务。
