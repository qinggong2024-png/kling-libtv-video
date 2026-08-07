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

健康检查同时比对磁盘后端源码与运行中 API 的 SHA-256 指纹。源码更新但 API 仍是旧进程时，
`apiSourceRevision` 会返回 `FAIL`；自启动 watchdog 会在下一轮检查中受控重启当前工作区的
API 和关联 Runner。首次部署此守卫后，需要重新安装或重启一次 watchdog，使常驻进程加载
新版脚本：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\manage-local-autostart.ps1 -Action Install -Mode Lan
```

发布后可运行真实浏览器冒烟检查。它会访问图片中心、视频制作、任务、内容库、管理中心全部
栏目和设置页，并在空白页、未捕获异常、`console.error` 或渲染器崩溃时返回非零退出码：

```powershell
Set-Location frontend
$env:UI_SMOKE_BASE_URL='http://127.0.0.1:5173/'
# 共享登录环境还需通过 UI_SMOKE_USERNAME / UI_SMOKE_PASSWORD 提供管理员账号。
npm.cmd run smoke:ui
```

报告写入 `var/reports/ui-smoke.json`。密码只从进程环境变量读取，不写入命令参数或报告。

## 视频生成 API 接入

新生产任务可由管理员在可灵官方 API 与 WaveSpeed 视频 API 之间切换。旧 LibTV、可灵 API、
WaveSpeed 或可灵 CLI 任务始终按 attempt 中已持久化的具体 Provider 查询和下载，切换默认通道
不会改写或重复提交历史任务。

Kling 的新生产任务统一使用官方 API 2.0。现有官方 CLI 只用于查询和下载已经提交的历史
attempt，不再作为可选的新任务后端。API 使用单个服务端 API Key，不使用旧版 Access Key /
Secret Key JWT：

管理员可在“管理中心 → 可灵官方 API”中选择当前视频通道，并启停可灵 API、替换或清除
API Key，以及调整 API
模型、时长、画幅、分辨率、音频、多镜头及提交/查询并发。Windows 下密钥使用
DPAPI 与受限 ACL 保存，页面和状态接口只返回“是否已配置”，不会回显密钥。API 进程立即应用
新配置，独立 Runner 在下一调度周期检测并加载；已提交任务继续使用其持久化 Provider。

以下环境变量仍可作为首次启动的默认配置；管理后台首次保存后，以共享安全配置为准：

```dotenv
KLING_PROVIDER_BACKEND=api
KLING_API_ENABLED=true
KLING_API_KEY=<从可灵开发者后台配置到部署环境>
KLING_API_BASE_URL=https://api-singapore.klingai.com
KLING_API_MODEL=kling-3.0-omni
KLING_API_DURATION=10
KLING_API_ASPECT_RATIO=9:16
KLING_API_RESOLUTION=1080p
KLING_API_AUDIO=off
KLING_API_MULTI_SHOT=true
KLING_API_MAX_SUBMIT_CONCURRENCY=1
KLING_API_MAX_POLL_CONCURRENCY=4
KLING_API_ENABLE_PAID_INTEGRATION_TEST=false
```

`KLING_PROVIDER_BACKEND` 接受 `api` 或 `wavespeed`。选择 `wavespeed` 前，需要先在同一管理
页面配置并启用 WaveSpeed；只有保存后创建的新任务才使用新通道。

API 默认关闭，不会自动产生付费请求。无密钥 Dry Run：

```powershell
uv run python scripts/kling_api_dry_run.py --storyboard-dir C:\path\to\storyboards `
  --prompt-file C:\path\to\prompt.txt
```

完整接口核验、配置、测试和回滚说明见
[`KLING_API_INTEGRATION_REPORT.md`](KLING_API_INTEGRATION_REPORT.md)。

配置 API Key 只会显示 `KLING_API_CONFIGURED_UNVERIFIED`，不会伪装为 READY。状态检查通过
官方任务查询端点执行一次只读鉴权校验；它不创建媒体，也不消耗生成额度。只有该校验成功后才
显示 `KLING_API_READY` 并允许新任务通过预检。

### WaveSpeed 图片与视频生成

图片中心通过 WaveSpeed 接入 GPT Image 2 和 Nano Banana 2。管理员在“管理中心 →
可灵官方 API → WaveSpeed API”中保存、替换或清除 API Key，并启用通道及执行
只读连接验证。密钥沿用 Windows DPAPI 与受限 ACL 保存，浏览器只能读取配置状态，不能读取
密钥明文。WaveSpeed 视频默认使用 Kling O3 Pro reference-to-video，模型 ID、时长、画幅和
声音均可在管理页面修改。后台安全配置优先于环境变量；清除后台覆盖后会回退到环境变量并
显示凭据来源。

首次启动可使用以下后备配置：

```dotenv
WAVESPEED_ENABLED=false
WAVESPEED_API_KEY=
WAVESPEED_API_BASE_URL=https://api.wavespeed.ai/api/v3
WAVESPEED_MAX_SUBMIT_CONCURRENCY=1
WAVESPEED_MAX_POLL_CONCURRENCY=4
WAVESPEED_VIDEO_PROVIDER_NAME=wavespeed_video
WAVESPEED_VIDEO_MODEL=kwaivgi/kling-video-o3-pro/reference-to-video
WAVESPEED_VIDEO_DURATION=10
WAVESPEED_VIDEO_ASPECT_RATIO=9:16
WAVESPEED_VIDEO_SOUND=false
```

视频适配器通过 `/media/upload/binary` 上传参考图，通过 `/{model-id}` 提交任务，并轮询
`/predictions/{id}/result`。当前固定模板使用多参考图，因此配置的模型必须是
`reference-to-video` 类型；可灵官方 Element ID 不会跨 Provider 复用。

图片中心提交前会显示模型和预计生成张数并要求二次确认。服务端保存用户归属、幂等键、远端
prediction ID、状态和输出文件；浏览器只轮询本地批次 ID，不能用任意远端 ID 查询其他用户
的结果。单批最多创建 40 个 prediction；创建接口会同步完成参考图上传和远端任务提交，但不
等待图片生成完成。当前版本尚未使用跨进程持久提交队列，部署时应保留付费暂停开关，并避免
在多个 API worker 上同时放大付费提交并发。真实付费接口验收还需要显式确认：

```powershell
uv run python scripts/test_wavespeed.py `
  --model nano-banana-2 `
  --mode edit `
  --prompt-file .\prompt.txt `
  --image .\references\model.jpg `
  --image .\references\product.png `
  --aspect-ratio 9:16 `
  --resolution 2k `
  --execute-paid `
  --confirm I_ACCEPT_WAVESPEED_CHARGES
```

以下 CLI 路径仅为历史 attempt 恢复保留。

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

CLI 的模型、时长、画幅、图片数量和参数名全部以 `who_am_i` / `tool_list` 的实时返回为准。
需要恢复历史 CLI attempt 时，应在运行 Runner 的同一 Windows 服务账号下保留原 OAuth
登录态，并通过环境变量显式启用恢复通道：

```dotenv
KLING_CLI_ENABLED=true
KLING_CLI_EXECUTABLE=kling
KLING_CLI_DEFAULT_MODEL=<who_am_i 返回且支持 image_to_video 的模型>
KLING_STORYBOARD_FALLBACK_MODE=disabled
KLING_ENABLE_PAID_INTEGRATION_TEST=false
```

`KLING_CLI_ENABLED` 不会让 CLI 接收新提交，只允许 Runner 查询和下载已有远端 task ID。
默认值为 `false`，测试也不会发起付费生成。多分镜超过实时能力时默认明确报错，不会
静默丢弃图片；只有业务明确接受首尾帧语义时才可设置
`KLING_STORYBOARD_FALLBACK_MODE=first_last_frame`。Kling 任务会按“分镜图在前、产品参考图
在后”的固定顺序上传，并在 prompt 中明确：分镜图只控制场景、构图、动作和镜头顺序，产品图只
约束服装款式、面料、颜色、印花、Logo 和文字细节。两类图片合计受实时 `imageInputLimit`
限制；系统不会静默丢图。提交成功后保存 CLI 返回的
`generationId`，Runner 使用 `query_tasks` 轮询并从 `works[].url` 原子下载结果；进程重启会
继续查询原任务，不会重复提交。

UNKNOWN 风险使用短时、分层熔断，不再修改全局 `paidSubmissionsPaused`：

- 单条 UNKNOWN 只隔离原 attempt，禁止原意图自动重投，不影响其他任务。
- 同一用户在同一 provider 的 30 分钟窗口内出现至少 2 个不同任务的 UNKNOWN，只暂停该用户
  在该 provider 上的新提交。
- 同一 provider 在 10 分钟内至少 5 个不同任务、覆盖至少 3 个用户、至少 6 条有效样本且
  UNKNOWN 比例达到 50%，才打开 provider 级熔断；其他 provider 继续运行。
- 动态熔断随时间窗口或人工对账结果自动收敛；管理员手动设置的全局/付费暂停仍独立生效。

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

管理员在“可灵官方 API”页保存的可灵 API Key，以及“流程与分析”页保存的分析服务 Key，
均不会回显。Windows 上的凭据文件使用机器级 DPAPI
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
