# LibTV 固定视频生产 Agent

面向 Windows 的 FastAPI + React 视频生产程序。每个产品任务固定生成两个 10 秒、9:16、
Kling O3 高品质静音视频：`STABLE` 稳定展示版和 `DYNAMIC` 动态展示版。所有 LibTV 操作
只调用官方 `libtv` CLI。

## 默认安全状态

示例配置默认使用 `LIBTV_ADAPTER_MODE=fake`、`LIBTV_EXECUTION_MODE=dry-run`、
`PAID_GENERATION_ENABLED=false`、`PAID_SUBMISSIONS_PAUSED=true`。这个组合不会调用远端写
操作，更不会执行付费边界：

```text
libtv node <nodeKey> --project <projectUuid> --run
```

即使 API 或 Runner 上层误调用，`RealLibTVAdapter.run_generation()` 仍会在创建进程前检查：

1. `LIBTV_EXECUTION_MODE=live`
2. `PAID_GENERATION_ENABLED=true`
3. `PAID_GENERATION_CONFIRMATION=I_ACCEPT_LIBTV_POINT_CHARGES`

测试环境禁止设置前两项。运行时数据库中的 `paidSubmissionsPaused` 还是独立的第四道门禁。
拦截会记录安全日志，但不会记录 Cookie、令牌或确认值。

图片分析还有独立的故障保护：`OPENAI_ANALYSIS_TIMEOUT_SECONDS`（默认 180 秒）是 4 张以内
素材的基础等待时间；超过 4 张后，每张按
`OPENAI_ANALYSIS_TIMEOUT_PER_EXTRA_IMAGE_SECONDS`（默认 45 秒）递增，最长等待 600 秒。
分析在 API 后台继续执行，前端只轮询任务状态，页面等待超时或切换页面不会取消分析。
`ANALYSIS_STALE_AFTER_SECONDS`（默认 660 秒）和
`ANALYSIS_RECOVERY_POLL_SECONDS`（默认 30 秒）由 API 启动巡检和周期巡检使用；任务阶段和心跳会
持久化为 `QUEUED`、`PREPARING_IMAGES`、`PROVIDER_RUNNING`、`VALIDATING`，供页面持续查询真实活性。
`ANALYSIS_SHUTDOWN_GRACE_SECONDS`（默认 15 秒）限制 API 退出时的等待时间，超过后会取消仍在运行的
分析任务。超时、供应商
异常或请求取消会把任务写回 `ACTION_REQUIRED`；进程重启后，超过僵尸阈值仍停在 `ANALYZING`
的任务也会被原子回收并记录审计事件，不会重新提交生成。

## 安装和启动

要求 Python 3.11、`uv`、Node.js、FFmpeg/ffprobe、官方 `libtv 1.1.1`。在线部署还要求
PostgreSQL 和 MinIO；纯本地 mock 测试使用 SQLite 和本地对象存储，不依赖 Docker。

```powershell
uv sync --all-extras
Set-Location frontend
npm.cmd install
Set-Location ..
Copy-Item .env.example .env
docker compose -f infra/compose.yaml up -d
uv run alembic -c backend/alembic.ini upgrade head
uv run uvicorn libtv_agent.app:create_app --factory --app-dir backend/src --reload
```

本地开发建议使用统一启动脚本；它会自动迁移数据库、启动 API/Runner 和前端，并等待 API
及前端代理都通过 readiness 检查：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-local-stack.ps1
```

投入团队使用时，通过局域网启动脚本启用账号登录并输出其他设备可访问的地址：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-lan-stack.ps1
```

脚本会自动选择当前局域网 IPv4、生成并持久化本机 Session 密钥，同时保持 API 只监听本机，
由前端同源代理访问。首次使用前创建管理员账号：

```powershell
uv run python scripts/create_user.py lan-admin --role ADMIN
```

手机、平板或其他电脑与服务器处于同一可信网络时，打开脚本输出的
`http://<服务器局域网 IP>:5173`。如果 Windows 将当前网络标记为“公用网络”，需要先将可信
局域网改为“专用网络”，或在防火墙中仅为该网络放行 Node.js 的 TCP 5173 入站访问。

Windows 当前用户登录后自动启动，并在 API 或前端意外退出时自动恢复：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\manage-local-autostart.ps1 -Action Install
```

需要长期供局域网设备使用时，将自启动切换为带账号登录的 `Lan` 模式：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\manage-local-autostart.ps1 -Action Install -Mode Lan
```

查看或移除自启动任务：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\manage-local-autostart.ps1 -Action Status
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\manage-local-autostart.ps1 -Action Uninstall
```

API 默认是 `http://127.0.0.1:8000`，前端默认是 `http://127.0.0.1:5173`。需要排查端口、
数据库迁移、Runner 或代理状态时运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\check-local-services.ps1 -RequireFrontend
```

## 可灵官方 CLI 接入

程序现在同时支持 `LibTV` 和 `Kling` 两个视频生成 provider。已有 LibTV 任务和命令路径保持
不变；provider 会写入每个任务和生成尝试，不会在任务执行期间自动切换。

官方 Skill 已安装到 `.agents/skills/kling-cli`。安装 CLI 前必须先确认账号区域，不能混装：

```powershell
# 中国区账号（klingai.com）
npm.cmd install --global @klingai/cli-cn --registry=https://registry.npmjs.org

# 海外区账号（kling.ai）
npm.cmd install --global @klingai/cli-global --registry=https://registry.npmjs.org
```

只执行与账号区域匹配的一条命令，然后在运行 API 和 Runner 的同一 Windows 服务账号下完成
浏览器 OAuth：

```powershell
kling login
kling who_am_i --quiet --skill-name kling-cli --skill-version 0.1.3
kling tool_list --quiet --skill-name kling-cli --skill-version 0.1.3
```

模型、时长、画幅、图片数量和参数名全部以 `who_am_i` / `tool_list` 的实时返回为准，程序不写死
模型名。管理后台可查看 CLI、登录和能力状态，可通过浏览器 OAuth 登录、重新登录、退出账号，
并手动刷新能力缓存。启用前至少设置：

```dotenv
KLING_CLI_ENABLED=true
KLING_CLI_EXECUTABLE=kling
KLING_CLI_DEFAULT_MODEL=<who_am_i 返回且支持 image_to_video 的模型>
KLING_STORYBOARD_FALLBACK_MODE=disabled
KLING_ENABLE_PAID_INTEGRATION_TEST=false
```

默认 `KLING_CLI_ENABLED=false`，测试也不会发起付费生成。多分镜超过实时能力时默认明确报错，不会
静默丢弃图片；只有业务明确接受首尾帧语义时才可设置
`KLING_STORYBOARD_FALLBACK_MODE=first_last_frame`。提交成功后保存 CLI 返回的
`generationId`，Runner 使用 `query_tasks` 轮询并从 `works[].url` 原子下载结果；进程重启会
继续查询原任务，不会重复提交。

常见恢复方式：

- `KLING_CLI_NOT_INSTALLED`：为正确区域安装 CLI，并重启 API/Runner。
- `KLING_CLI_NOT_AUTHENTICATED`：使用服务账号重新运行 `kling login`。
- `KLING_CAPABILITY_FETCH_FAILED`：先运行 `kling who_am_i` 和 `kling tool_list` 排查，再在管理
  后台刷新能力。
- 未知远端状态：任务保留为已提交待人工检查，系统不会擅自重新扣费。

当前机器的实际接入验收结论见
[`KLING_CLI_INTEGRATION_REPORT.md`](KLING_CLI_INTEGRATION_REPORT.md)。

staging/production 使用服务端 Session 和 CSRF 双重校验，必须通过 HTTPS 访问。首次部署先创建
受邀账号，随后使用前端登录页进入：

```powershell
uv run python scripts/create_user.py production-admin --role ADMIN
```

### 局域网账号登录

仅在可信局域网内通过 HTTP 使用时，可以继续保留 `APP_ENV=development`，并显式启用服务端
Session 登录。不要把此配置用于公网、端口转发或不受信任的访客网络：

```dotenv
SHARED_AUTHENTICATION_ENABLED=true
SESSION_COOKIE_SECURE=false
SESSION_SECRET=<至少 32 字节的随机值>
APP_PUBLIC_ORIGINS=http://<服务器局域网 IP>:5173
```

重启 API 后，先在服务器终端创建第一个管理员：

```powershell
uv run python scripts/create_user.py lan-admin --role ADMIN
```

随后从 `http://<服务器局域网 IP>:5173` 打开登录页。管理员可在“管理中心 → 成员账号”创建
普通用户、重置密码或停用账号。局域网模式仍启用 Argon2 密码哈希、服务端 Session、CSRF、
角色权限和审计；只有 Cookie 的 HTTPS 限制被显式关闭。

管理员在设置页保存的 LibTV/OpenAI Key 不会回显。Windows 上的凭据文件使用机器级 DPAPI
加密，并把 NTFS ACL 限制为当前服务账号、SYSTEM 和 Runner 服务账号；共享环境如果无法应用
Runner ACL，会拒绝保存凭据。

LibTV CLI 的浏览器登录凭据独立保存在 `LIBTV_CONFIG_DIR`（默认
`var/runtime/libtv`）。API、Runner 和独立 command-host 都显式使用同一目录，不依赖各自的
Windows 用户配置目录。账号过期时 Runner 会把运行状态标记为 `libtvAuthRequired`、暂停新的
付费确认并停止认领新的生成命令；已经排队的任务和积分预留不会被误判为已提交。

管理员重新登录只需运行官方 CLI 封装脚本：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\refresh-libtv-login.ps1
```

脚本先执行 `libtv account info`，仅在返回未登录时打开 `libtv login web --open`，登录后再次
校验；凭据目录依次读取 `-ConfigDir`、当前环境变量、项目 `.env` 和默认值。Runner 最多在
`LIBTV_AUTH_CHECK_SECONDS` 后自动清除登录告警，但不会自动解除原有的
`paidSubmissionsPaused` 付费门禁。服务安装脚本会给安装管理员和 Runner 服务账号授予该目录
所需权限；其他管理员操作受保护目录时应使用管理员 PowerShell。需要立即重新检测时可显式
传入 `-RestartRunner`。

## 免费验证

完整本地检查不会调用真实生成：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\check.ps1
```

登录和模型只读 canary 只允许版本、账号、工作区、画布和模型查询，并在报告中证明上传、
建节点、`--run` 均为 0：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\libtv-readonly-canary.ps1
```

报告位于 `var/reports/`，mock/replay fixture 位于 `backend/tests/fixtures/`。

## Prepare-only

`prepare-only` 会使用真实 CLI 创建画布/分组、上传素材、创建并配置 A/B 视频节点、读回核对，
然后停在 `WAITING_FOR_SEAL`。它不会创建可派发的生成命令。

```dotenv
LIBTV_ADAPTER_MODE=real
LIBTV_EXECUTION_MODE=prepare-only
LIBTV_WORKSPACE_ID=<专用工作区 ID>
PAID_GENERATION_ENABLED=false
PAID_GENERATION_CONFIRMATION=
PAID_SUBMISSIONS_PAUSED=true
```

精确 argv、参数摘要、prompt hash、预计生成数和成本警告保存到
`var/runner/previews/<task-id>.json`，也可通过
`GET /api/v1/tasks/<task-id>/generation-preview` 查看。重复确认会复用已验证的物化 saga，
不会重复上传或创建节点。

## 真实生成

只有在审查 preview 后才临时设置：

```dotenv
LIBTV_EXECUTION_MODE=live
PAID_GENERATION_ENABLED=true
PAID_GENERATION_CONFIRMATION=I_ACCEPT_LIBTV_POINT_CHARGES
PAID_SUBMISSIONS_PAUSED=false
```

随后重新确认 `WAITING_FOR_SEAL` 任务并由 Windows Runner 执行。一次产品任务恰好包含两个
正式节点，每个节点 `count=1`；多图分镜会设置 `smartStoryboard=true`。成功后 CLI 返回的
CDN URL 会交给官方技能内置 PowerShell
下载器，以 Auto 网络模式、8 分段和断点续传下载，再经 ffprobe、尺寸、时长和 SHA-256
校验。下载失败只复用同一 URL 和目标文件，不会重新生成。

本次两套衣服验收使用两阶段脚本。`prepare` 只做远端免费准备和命令预览；`execute` 还必须
同时给出 `--execute-paid` 与固定确认短语。脚本使用跨进程互斥锁；已有验收进程运行时，
其他窗口会在读取或修改验收状态前直接退出。每套只能执行一次，两套合计生成 4 条视频：

```powershell
uv run python scripts/acceptance_libtv.py prepare --set-id 1 --title "7.27-1" `
  --image "<按确认顺序重复传入 --image>"

uv run python scripts/acceptance_libtv.py execute --set-id 1 --execute-paid `
  --confirmation I_ACCEPT_LIBTV_POINT_CHARGES
```

验收状态保存在 `var/acceptance/state.json`。真实 CLI 日志、preview、断点续传状态和下载文件
保存在 `F:\LibTV-Outputs\20260727-libtv-acceptance\set-<编号>\`。

完成后立即恢复：

```dotenv
LIBTV_EXECUTION_MODE=dry-run
PAID_GENERATION_ENABLED=false
PAID_GENERATION_CONFIRMATION=
PAID_SUBMISSIONS_PAUSED=true
```

完整故障处理、付费边界和首次使用观察项见
[`docs/runbooks/free-preflight-and-paid-boundary.md`](docs/runbooks/free-preflight-and-paid-boundary.md)。
