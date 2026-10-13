# Sprint Report · Creative Workflow MVP-2C

日期：2026-10-11
范围：`director_fixed` 视频执行的服务层 preflight/plan 前置合同
testing：`E:/Projects/libtv自动化生成`，`codex/testing`
实际 main：`C:/Users/Reel/Documents/libtv-auto-main-sync`，`main`

## 完成

新增只读 `creative_video_bridge` 服务：

```text
FIRST_FRAME 人工 QUALIFIED + select
→ SHOT_01 storyboard 人工 QUALIFIED + select
→ 校验包、授权、Prompt/Preservation、权限、状态、哈希和逐级映射
→ 返回 director_fixed preflight plan
```

计划同时返回真实的 CreativeTask、FIRST_FRAME、SHOT_01 package、candidate、
batch、item、output 映射和源图哈希；锁定的 storyboard Prompt、Preservation
hash、文本合同 hash 和完整冻结文本合同随计划返回。`provider_submission_allowed`
和 `deliverable_eligible` 固定为 `false`，Fake/Replay 来源继续保持
`OFFLINE_SYNTHETIC_ONLY`。

## 修改

仅修改以下白名单文件：

- `backend/src/libtv_agent/services/creative_video_bridge.py`
- `backend/tests/test_creative_video_bridge.py`
- 本报告

没有修改 `fixed_video_tasks.py`、视频 API、OpenAPI、数据库模型、migration、前端或
旧 automatic/custom 行为。Bridge 不调用 `compile_video_plan`、`apply_video_learning`，
不创建视频任务、attempt、Provider URL、账本记录或生产提交。

## 测试

testing：

- `backend/tests/test_creative_video_bridge.py`：10 项通过，覆盖双源映射、
  可重复读取且不新增记录、状态失效、UNKNOWN/stopped/revoked/过期/错镜、
  未选择、权限/映射/人工资格拒绝，以及旧视频规划函数负调用断言。
- Creative Workflow、Storyboard、图片 bridge、媒体隔离、文字合同、恢复/停止、
  fixed video/image 回归选集：全部通过。
- scoped Ruff：通过。
- `git diff --check`：通过。

main 独立复验：

- 仅同步以上三个白名单文件后，在实际 `main` 独立运行相同专项和 scoped 回归。
- `backend/tests/test_creative_video_bridge.py`：10 项通过。
- Creative Workflow、Storyboard、图片 bridge、媒体隔离、文字合同、恢复/停止、
  fixed video/image 回归选集：全部通过。
- scoped Ruff：通过。
- `git diff --check`：通过。
- 三个白名单文件 SHA-256 与 testing 一致。

## 限制

本包未调用真实视频 Provider、未验证真实视频入参接收、像素质量、视频生成、
费用/账本、PostgreSQL 多 worker、部署、服务重启或生产数据库迁移。Fake/Replay
仅证明静态服务合同和来源隔离，不能作为正式视频结果、QUALIFIED 交付物或生产就绪证据。
