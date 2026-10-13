# Sprint Report · Creative Workflow MVP-2A

日期：2026-10-11
范围：离线 Fake 模式单个 `VIDEO_STORYBOARD` shot 合同闭环
testing：`E:/Projects/libtv自动化生成`，`codex/testing`
实际 main：`C:/Users/Reel/Documents/libtv-auto-main-sync`，`main`

## 完成

在既有人工合格并选择的 `FIRST_FRAME` 后，补齐单镜 `SHOT_01` 的离线合同：

```text
FIRST_FRAME QUALIFIED + select
→ authorize scope=VIDEO_STORYBOARD, shot_ids=["SHOT_01"]
→ generate
→ SHOT_01 candidate / batch / item / output
→ review
→ select
```

`FIRST_FRAME` 与 `VIDEO_STORYBOARD` 候选、审核、选择分开保存。`SHOT_01`
映射持久保存到 `shot_mappings`，并保留 append-only package、attempt、review、
selection 记录。Fake 输出继续标记 `OFFLINE_SYNTHETIC_ONLY`，不能用于交付。

## 修改

仅修改以下白名单文件：

- `backend/src/libtv_agent/creative/workflow.py`
- `backend/src/libtv_agent/services/creative_workflow.py`
- `backend/tests/test_creative_workflow_storyboard.py`
- 本报告

`PackageRevision`、`Authorization`、`StageAttempt`、`Review` 和 `Selection`
增加用途/镜号字段；storyboard 合同严格限制为单个 `SHOT_01`，没有通用多镜、
排序或多包推进。Storyboard 授权必须依赖服务端已持久的首帧人工选择，并在
授权时建立唯一 Fake package。生成严格校验授权、包、镜号、商品版本、文本
合同和 UNKNOWN 状态。

旧 `FIRST_FRAME` 默认授权、修订包、`NO_PROGRESS` 顺序、review/select/stop/
revoke、幂等、恢复和顶层 registry 篡改校验保持兼容。没有修改 API 路由、
OpenAPI、数据库模型、migration、Provider 或旧 automatic/custom 视频行为。

## 测试

testing：

- Creative Workflow 聚合 scoped pytest：42 项通过。
- MVP-2A 专项 pytest：3 项通过。
- scoped Ruff：通过。
- scoped 空白检查：通过。
- 覆盖首帧前置门、唯一 `SHOT_01`、过期授权、错误镜号、UNKNOWN 阻断、
  batch/item/output 映射、人工 review/select 和持久记录。

main：

- Creative Workflow 聚合 scoped pytest：42 项通过。
- MVP-2A 专项 pytest：3 项通过（包含在聚合结果中）。
- scoped Ruff：通过。
- scoped 空白检查：通过。
- 4 个白名单文件同步成功，SHA-256 与 testing 一致。

## 发现问题

- 一次聚合命令最初因 PowerShell 不展开 pytest 通配符而未运行测试，改为
  `rg --files` 枚举后通过。
- 一次旧回归因首帧授权错误绑定修订包而返回 `PACKAGE_MISMATCH`；已恢复旧
  授权语义。
- 一次旧 text-contract 回归因首帧校验绕过顶层 registry；已改为首帧继续
  使用顶层 registry，只有 `SHOT_01` 使用按包合同。
- Fake/Replay 未调用 Provider，未执行真实像素质量验证、生产数据库迁移、
  部署、服务重启或正式版验收；Fake 结果不可交付。

## 下一步

后续 `director_fixed` 视频入口仍需独立合同和人工授权，不属于 MVP-2A。
多镜 storyboard、排序、真实 Provider、真实质量和生产迁移继续保持未实现。
