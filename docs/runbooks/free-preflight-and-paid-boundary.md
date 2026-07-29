# 免费预检、付费边界与故障处理

## 模式

| 模式 | 远端查询 | 画布/上传/节点写入 | `node --run` |
| --- | --- | --- | --- |
| `dry-run` | 允许 | 拦截 | 拦截 |
| `prepare-only` | 允许 | 允许 | 拦截 |
| `live` | 允许 | 允许 | 仅在双重确认及运行时解锁后允许 |

测试进程若配置 `live` 或启用付费开关会直接启动失败。Real Adapter 是最后一道集中式防线，
不依赖界面按钮或 API 调用方正确实现。

## 免费检查顺序

1. 运行 `scripts/check.ps1`，要求 Ruff、pytest、离线 Alembic、前端 lint/build 全部通过。
2. 运行 `scripts/libtv-readonly-canary.ps1`。检查报告中的 `nodesCreated=0`、`uploads=0`、
   `nodeRuns=0`、`paidOperations=0`。
3. 核对 CLI 版本、当前账号 hash、目标工作区和画布可读。
4. 核对 Kling O3 实时 schema：`mixed2video` 最多 7 图、prompt 最多 2000 字、10 秒、
   9:16、high、enableSound=off、count=1；多图任务为 smartStoryboard=true。
5. 用 fake/replay 完成排队、处理中、成功、终态失败、登录失效、参数错误、网络异常、
   非零退出、下载中断恢复和 UNKNOWN 对账测试。
6. 使用 `prepare-only` 后审查 `var/runner/previews/<task-id>.json`，确认每个产品任务恰好
   两条命令，分别是 STABLE 与 DYNAMIC，每条预计生成 1 个视频。

## LibTV 登录失效

Runner 使用 `LIBTV_CONFIG_DIR`（默认 `var/runtime/libtv`）作为统一 CLI 凭据目录，并按
`LIBTV_AUTH_CHECK_SECONDS` 周期执行只读的 `libtv account info`。`401`、`未登录`或等价登录
错误统一记为 `LIBTV_AUTH_REQUIRED`：自动暂停新的付费确认、停止认领新的生成命令，但不把
排队任务标记为失败，也不把积分改成未知扣费。

管理员在项目根目录执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\refresh-libtv-login.ps1
```

脚本仅调用官方 `libtv account info` 和 `libtv login web --open`。登录恢复后 Runner 自动清除
`libtvAuthRequired`；`paidSubmissionsPaused` 必须由管理员按原有付费边界显式解除。

## 首次真实执行观察项

- 输入顺序和角色：真实分镜按确认顺序，白底图/款式图不得成为独立镜头。
- 新画布是否落在 `LIBTV_WORKSPACE_ID` 指定的专用工作区。
- 上传 nodeKey 数量、顺序和读回的 `mixedListOrder` 是否一致。
- 两个视频节点均为 Kling O3、10 秒、9:16、high、静音、count=1；多图任务启用智能分镜。
- 两条正式 `--run` 只能各启动一次；发现 UNKNOWN、command-host 丢失或任务 ID 已出现时，
  不得重提。
- 保存 command-host manifest、stdout、stderr、terminal result、taskId、开始/结束时间。
- 下载失败只重跑下载器，不得重跑节点。
- 技术校验检查 MP4 可解码、9:16、9-11 秒、无音频、SHA-256 和字节数。
- 完成后重新启用 `paidSubmissionsPaused` 并关闭两个环境级付费开关。

## 失败处理

在生成前失败且没有任务 ID时，记录 `FAILED_BEFORE_SUBMIT`；仍不自动重试付费命令。
只要 stderr/stdout 出现任务 ID、进程在 LAUNCH_STARTED 后失联，或无法确认服务端是否接收，
统一标记 `UNKNOWN_AFTER_SUBMIT`，冻结新的付费提交并使用 `read_node` 只读对账。

LibTV CLI 1.1.1 当前不提供余额或准确扣点字段。成功终态能证明生成已完成，但实际积分数需从
LibTV 账单侧人工核对；不能因为余额不可见而再次提交。

日志位置：

- `var/runner/command-hosts/logs/`
- `var/runner/command-hosts/results/`
- `var/runner/command-hosts/manifests/`
- `var/runner/previews/`
- `var/reports/`

本次专用两套验收的 preview、command-host 日志、结果和下载文件位于
`F:\LibTV-Outputs\20260727-libtv-acceptance\set-<编号>\`，次数状态位于
`var/acceptance/state.json`。两次指两套衣服各一次验收，每套运行 STABLE/DYNAMIC 两个正式
节点，合计最多 4 条视频，不表示可以对失败节点自动重试。
