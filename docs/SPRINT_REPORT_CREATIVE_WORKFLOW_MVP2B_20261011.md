# Sprint Report · Creative Workflow MVP-2B

日期：2026-10-11
范围：单镜导演首帧到现有图片入口的服务端桥接前置合同
testing：`E:/Projects/libtv自动化生成`，`codex/testing`
实际 main：`C:/Users/Reel/Documents/libtv-auto-main-sync`，`main`

## 完成

新增 `creative_image_bridge` 服务层前置计划：

```text
FIRST_FRAME 人工 QUALIFIED + select
→ 校验 CreativeTask 当前状态、包合同、权限、来源哈希
→ 校验真实 batch/item/output 映射仍为 OFFLINE_SYNTHETIC_ONLY
→ 返回不可提交 Provider、不可升级普通 ImageGenerationOutput、不可交付的桥接计划
```

计划返回真实 `creative_task/package/candidate/batch/item/output` ID 映射、
`qualification_scope=OFFLINE_SYNTHETIC_ONLY`、稳定幂等键、状态有效性 token 和下一步
`REAL_PROVIDER_ADAPTER_REQUIRED`、`HUMAN_PROVIDER_AUTHORIZATION_REQUIRED`。不返回
`fake://` 或其他媒体 URL，不调用 Provider，不写入新的生产批次。

## 修改

- `backend/src/libtv_agent/services/creative_image_bridge.py`
- `backend/tests/test_creative_image_bridge.py`
- 本报告

没有修改 API 路由、OpenAPI、数据库 migration、前端、旧 automatic/custom 行为或
`.env`。旧图片入口仍由现有 `is_offline_synthetic_output`、人工审核和上传边界拒绝
Fake 来源；本包没有把 Creative Fake 输出提升为普通图片 `QUALIFIED` 或 Deliverable。

## 测试

testing：

- `backend/tests/test_creative_image_bridge.py`：9 项通过。
- Creative Workflow、Storyboard、Accounting、Recovery、Stop Audit、Text Contract、
  Media Isolation、旧图片批次和媒体回归：共 74 项通过。
- `backend/tests/test_creative_migration_repair.py`：3 项通过。
- scoped Ruff：通过。
- `git diff --check`：通过。
- 桥接计划重新读取持久 task 真源，并复核对象存储哈希、商品版本、不可变 Creative
  证据、授权期限及 batch/item/output 逐级映射；加固后上述结果保持通过。

完整 Creative migration integrity 回归仍有 2 项既存失败：`creative_record` 与
`creative_command` 的直接 SQL 删除未被当前 testing 迁移触发器拒绝。这是协调表已记录
的 CW-3D/CW-3E 迁移缺口；本包禁止修改 migration，因此未扩大范围修复，也没有把它
误报为本包回归。

main 独立复验：

- 同一 74 项专项回归：通过。
- `backend/tests/test_creative_migration_repair.py`：3 项通过。
- scoped Ruff：通过。
- `git diff --check`：通过。
- 三个白名单文件 SHA-256 与 testing 一致。

## 限制

本包只交付桥接前置校验/计划，不创建真实 Provider adapter，不提交真实图片任务，
不验证真实 Provider 入参、像素质量、费用/账本、PostgreSQL 多 worker、生产部署或
生产数据库迁移。后续接入必须另有真实 Provider adapter 和人工授权合同。

## 白名单与同步

testing 验证通过后，只同步上述三个文件到实际 `main`，逐文件比较并保留 main 其他
未提交改动；已完成 main 独立专项复验。报告自身不写入 SHA-256，避免自引用导致值不稳定。
