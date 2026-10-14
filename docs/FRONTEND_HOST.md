# 前端常驻托管

`scripts\manage-frontend-host.ps1` 是只负责前端的常驻入口。它把 Vite 服务固定托管在局域网 `5173`，并在 Vite 进程意外退出时自动拉起。

它存在的理由很具体：后端已经由 `LibTVProductionApi` Windows 服务常驻（见 `docs/API_WINDOWS_SERVICE.md`），但前端原先依赖人手启动，一旦终端关闭或 `npm run dev` 崩掉，局域网入口就静默消失，而后端本身完全察觉不到。这个脚本补的就是这一段。

## 明确不做的事

同目录下的 `start-local-api.ps1` / `start-local-stack.ps1` 会做下面三件事，本脚本**一件都不做**：

- 不执行 `alembic upgrade`，因此不可能迁移生产数据库；
- 不启动 `local_runner.py`，因此不可能发起付费供应商请求；
- 不监听也不检查 `8000`，该端口属于 Windows 服务。

脚本只在 `5173` 上工作。它不会因为端口冲突去停止任何非本工作区所有的进程——本机端口被陌生进程占用时只报告，不杀。

## 命令

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\manage-frontend-host.ps1 -Action Status
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\manage-frontend-host.ps1 -Action Install -ProjectRoot 'E:\Projects\libtv自动化生成' -NodePath 'D:\New Folder\node.exe'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\manage-frontend-host.ps1 -Action Start
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\manage-frontend-host.ps1 -Action Stop
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\manage-frontend-host.ps1 -Action Uninstall
```

动作语义：

| Action | 作用 |
| --- | --- |
| `Status` | 只读。报告计划任务状态、触发条件数、`5173` 监听者与是否由本工作区所有、HTTP 是否可用、日志路径。 |
| `Serve` | 前台驻留循环，由计划任务调用，一般不手工执行。 |
| `Install` | 注册计划任务并立即启动，等待 HTTP 就绪后打印 `Status`。 |
| `Start` / `Stop` | 启动/停止。`Stop` 会先禁用任务再停止，并回收本工作区所有的监听进程——不禁用的停止没有意义，重复触发器一分钟内就会把它拉回来；`Start` 会先重新启用。 |
| `Uninstall` | 停止、注销任务，保留日志。 |

`Install` 不需要管理员权限：任务是当前交互用户 + `RunLevel Limited`。

以上 `Install` 是本地登录托管。正式版目前使用另行注册的 SYSTEM 开机任务，不能用普通
`Install` 覆盖它，否则会退回需要用户登录的启动方式。正式状态检查应明确指定
`-ProjectRoot 'C:\Users\Reel\Documents\libtv-auto-main-sync'`。

默认参数：`-HostAddress 0.0.0.0`、`-Port 5173`、`-TaskName 'LibTV Frontend Host'`、`-StartupTimeoutSeconds 40`。

## 为什么是 Vite 开发服务器

现状仍然是 Vite dev server，适合局域网验收，**不是**长期正式静态托管方案。正式部署应构建 `frontend/dist` 交给 IIS/Nginx，不能让常驻进程托管热更新服务。本脚本只是把"局域网入口不消失"这件事先兜住。

## 四个必须知道的行为约束

1. **Vite 的项目根来自工作目录。** 脚本先 `Set-Location` 到 `<ProjectRoot>\frontend` 再启动，与 `npm run dev --prefix frontend` 等价。从仓库根启动会服务一个没有 `index.html` 的目录，`/` 直接 404。
2. **登录任务不继承交互式 shell 的 PATH。** 本机 `node.exe` 不在机器 PATH 也不在 Program Files。脚本按 `-NodePath` → 机器 PATH → 用户 PATH → 当前进程 PATH 的顺序探测，并把解析出的绝对路径写进计划任务参数，所以后续登录不依赖 PATH 解析。
3. **计划任务的"失败重启"对手工启动的任务不生效。** 因此可靠性由两层承担：脚本内部的 supervisor 循环负责拉起 Vite 本身；任务上的 1 分钟重复触发器负责在任务进程被杀后复活宿主。`-MultipleInstances IgnoreNew` 保证第二层不会复制出第二个健康实例。回退：vite 被杀 → 内层在 5s 内拉起；宿主被杀 → 外层在 1 分钟内拉起。
4. **`Stop-ScheduledTask` 只杀任务进程，不杀它启动的 Vite 子进程。** 于是"有监听者但背后没有 supervisor"是一个正常状态，而不是健康状态。脚本遇到端口已被本工作区占用时**不退出**，而是转成该监听者的 supervisor，等它退出后再自己拉起新的——否则重复触发器会拿到一次空操作，留下一个没人看管的孤儿。同理，`-Action Stop` 必须一并禁用任务。

supervisor 退避：5s 起步、翻倍、封顶 60s；某次运行存活满 120s 视为健康并把退避重置回 5s。配置坏掉时退化成慢重试，不会变成紧凑空转。

任务触发器为 `AtLogOn` + 每分钟重复。注册时**不传** `-RepetitionDuration`——Task Scheduler 会拒绝 `[TimeSpan]::MaxValue` 序列化出的 `P99999999DT23H59M59S`，而省略该参数本身即表示无限重复。

## 日志

`var/logs/frontend.host.log`，由 `stack-logging.ps1` 统一写入并轮转，记录：宿主启动、解析到的 node 与 vite 路径、每次 Vite 启动/退出码/存活秒数、重启间隔。

本文件必须保持纯 ASCII：Windows PowerShell 5.1 会用 ANSI 代码页解码没有 BOM 的 `.ps1`，非 ASCII 字节会被静默改写。所有中文说明都放在文档里，不放进脚本注释。

## 验收记录（2026-09-25）

| 项目 | 结果 |
| --- | --- |
| 计划任务 | `LibTV Frontend Host`，`State=Running`，`triggers=2` |
| 监听 | `0.0.0.0:5173`，`node.exe` |
| 回环入口 | `http://127.0.0.1:5173/` → 200 `text/html` |
| 局域网入口 | `http://192.168.30.126:5173/` → 200 `text/html` |
| API 代理 | `http://127.0.0.1:5173/api/v1/health/ready` → 200，`X-LibTV-Maintenance: query-only` |
| 进程被杀后恢复 | 杀掉 Vite 后约 11s 内自动恢复（日志 `vite exited with code -1 after 14s; restarting in 5s`） |
| 宿主被杀后恢复 | `Stop-ScheduledTask` 后 Vite 子进程成为孤儿并留在端口上；下一分钟的触发实例发现端口已被本工作区占用，转为该孤儿的 supervisor 并保持 `Running`（日志 `frontend already served by PID 50940; supervising it until it exits`） |
| 端口被外部占用 | 只报告，不杀；不启动第二份 |

## 已知遗留

- 计划任务 `LibTV Local Stack Watchdog`（`-Mode Lan`）仍在注册表中。它调用 `watch-local-stack.ps1` → `start-local-stack.ps1` → `start-local-api.ps1`，会执行生产迁移、启动 Runner 并抢占 `8000`，与本方案的目标相冲突。本次未修改它，但在下一次登录时它可能触发。处理它之前应先确认整体自启动编排的归属。

## 2026-10-14 正式恢复与开机配置

本节更新上面的历史验收：正式入口为 `http://192.168.30.126:5173/`，
源码目录为 `C:\Users\Reel\Documents\libtv-auto-main-sync`，分支 `main`。
旧 `LibTV Local Stack Watchdog` 已核对为 Disabled，应继续保持禁用。

SYSTEM 的 PATH 包含一个空项，原解析器在检查显式 Node 前对空项调用 `Join-Path`，
导致任务退出码 1、日志只有 run start、5173 没有监听。解析器现在跳过空项及无法组合的路径；
动作异常写入 `frontend.host.log` 的 `UNHANDLED` 记录后继续抛出，保留任务失败状态。

当前正式任务已核对：

| 项目 | 配置 |
| --- | --- |
| 身份 | SYSTEM / ServiceAccount / Highest，不依赖交互用户登录 |
| 触发 | AtStartup + 每分钟重复，无截止日期 |
| 执行 | Windows PowerShell 5.1，Hidden，正式目录的 `-Action Serve` |
| Node | `D:\New Folder\node.exe` |
| 运行期限 | PT0S，不限时 |
| 恢复 | RestartCount 999、RestartInterval PT1M、StartWhenAvailable |
| 重入 | IgnoreNew；健康常驻时 0x800710E0 是重复启动被拒绝，不是 HTTP 故障 |
| 电池 | 允许启动，切换电池不停止任务 |

前端及代理 live/ready 均返回 200；ready 的数据库和 schema 检查通过。
非管理员读取 SYSTEM 进程时 CommandLine/ExecutablePath 可能为空，
此时 `OwnedByWorkspace=False` 不能单独证明是外部进程；需结合任务 Action、
启动日志、父进程和 HTTP 核对，不能据此强杀监听者。

回归检查只验证启动解析和失败日志，不启动服务器：

```powershell
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File scripts\test-frontend-host.ps1
```

普通用户关闭终端或退出登录后，SYSTEM 任务仍可运行；机器关机、睡眠或断电期间不能提供服务。
本次未执行整机重启或休眠演练，开机恢复仍需安排实际演练。
要摆脱这台电脑的开关机，部署目标必须是常开的服务器或独立主机：
构建前端交给 IIS/Nginx，反向代理 `/api`；将 API、数据库、运行数据和备份一起规划，
通过目标机 live/ready、登录和重启验收后再切换访问入口。真实密钥通过独立配置交付，
不经 Git 同步；付费执行、Runner 和生产写权限保持各自的授权边界。
