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
