# Kling 官方 CLI 接入报告

日期：2026-07-28  
工作区：`C:\Users\Reel\Documents\libtv自动化生成`

## 结论

Kling provider 的程序接入已完成，原有 LibTV 流程保留且不会被自动切换。当前机器已安装
中国区官方 CLI、完成浏览器 OAuth，并通过真实账号完成免费只读能力发现。本机 `.env` 已启用
Kling，默认选择实时确认可用的 `kling-video-v3_0_omni`。

实时合同支持最多 7 张参考图、10 秒和 9:16，具备承接现有多分镜输入的条件。但当前账号可用
灵感值为 0，尚未完成一次受控真实成片验收，因此暂不宣称与 LibTV 生产结果等价。

## 实机状态

| 检查项 | 结果 |
| --- | --- |
| 官方 Skill | 已安装，`.agents/skills/kling-cli` |
| Skill 版本 | `0.1.3` |
| 区域与 CLI | 中国区 `@klingai/cli-cn`，`kling-cli 0.1.3` |
| OAuth 登录 | 成功 |
| 真实 `who_am_i` | 成功 |
| 真实 `tool_list` | 成功 |
| 账户 | 免费版，可用灵感值 `0` |
| 付费生成探针 | 未执行，不产生扣费 |

真实 `tool_list` 返回了 `who_am_i`、`image_to_video`、`query_tasks`、`file_upload`、
`query_membership_and_credits` 等工具。真实 `who_am_i` 返回的图生视频模型包括：

- `kling-video-v2_5`
- `kling-video-v2_6`
- `kling-video-o1`
- `kling-video-v3_0_omni`
- `kling-video-v3_0`
- `kling-video-v3_0_turbo`

本项目的 O3 多分镜合同使用 `kling-video-v3_0_omni`：实时声明支持 1–7 张 `image_N`
参考图、3–15 秒、`16:9` / `9:16` / `1:1`、智能多镜头和音频开关。图片须为 PNG/JPG、
低于 4K、最大 30MB，宽高比不超过 1:2。本机账户当前可用档位为 720p。

## 已实现范围

- 通用视频 provider 合同，以及独立 `KlingOfficialCliAdapter`。
- 使用参数数组启动子进程，不拼接 shell 命令；覆盖超时、退出码、stdout/stderr 和 JSON 解析。
- 启动与管理端能力发现，能力缓存和显式刷新。
- 动态模型选择与参数校验；本机默认模型来自本次真实能力发现。
- 多分镜能力不足时默认拒绝；仅支持显式开启的首尾帧回退。
- 提交后持久化 `generationId`、provider、模型、远端状态、轮询时间、输出 URL 和错误码。
- `query_tasks` 独立轮询、未知状态降频、进程重启恢复、避免重复提交。
- 从 `works[].url` 下载到 `.part` 后原子落盘，并复用已验证文件。
- 前端 provider 选择、不可用原因、能力状态，以及管理员登录、重新登录、退出账号和刷新入口。
- 示例环境默认关闭 Kling，付费集成测试始终默认关闭；本机完成验收后已显式启用。
- 同时兼容旧版模型数组和当前 `image_to_video.models` 响应结构。
- 按选中模型区分首尾帧输入与 `image_1`…`image_7` 多参考输入，不会丢弃中间分镜。

## 数据库与接口

迁移 `a16c4f2e9b77_kling_provider_metadata.py` 仅新增字段和索引，不删除或重命名旧字段。

新增管理接口：

- `GET /api/v1/admin/kling/status`
- `POST /api/v1/admin/kling/capabilities/refresh`
- `POST /api/v1/admin/kling/login`
- `POST /api/v1/admin/kling/logout`

系统状态接口同时返回 Kling 的启用、安装、登录、版本、模型、图片输入上限和回退模式。

## 验证记录

自动测试在 Kling 关闭、LibTV dry-run、禁止付费提交的环境中执行；真实 CLI 验收只调用免费
只读命令：

- 后端：`134 passed, 2 skipped`
- 前端单元测试：`9 passed`
- 前端 ESLint：通过
- OpenAPI 合同：已重新导出并通过后端合同测试
- 真实适配器能力刷新：成功识别 6 个图生视频模型、7 图上限、10 秒和 9:16
- `image_to_video --help`、`query_tasks --help`、`file_upload --help`：成功读取实时声明

未执行任何会消耗可灵灵感值的命令。

## 上线前必做

1. 为账号充值或开通满足业务要求的会员档位。
2. 由业务负责人明确批准一次受控付费验收；保持提示词和参数，不做自动重投。
3. 验证真实输出的时长、9:16、分镜一致性、音频策略、下载和恢复流程。
4. 重启正式 API/Runner，在管理后台确认状态为 `KLING_CLI_READY`。

只有受控成片验收通过后，才建议将 Kling 设为生产默认 provider。
