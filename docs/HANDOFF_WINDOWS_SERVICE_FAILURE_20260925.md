# Windows API 服务故障交接文档

更新时间：2026-09-25  
适用服务：`LibTVProductionApi`  
交接对象：后续负责修改、部署或验收的 agent

## 1. 目标与边界

本次任务是将 LibTV 的维护 API 从前台 PowerShell 进程迁移到 Windows Service，服务默认使用 `query-only` 维护模式：

- 允许登录、认证、健康检查、系统状态和既有任务查询；
- 默认拒绝生成、确认、上传、供应商调用等写操作；
- 不启动 Runner，不执行供应商轮询、下载、结算，不执行数据库迁移；
- 服务绑定 `127.0.0.1:8000`，前端正式入口仍为 `http://192.168.30.126:5173/`。

相关代码和说明：

- `backend/src/libtv_agent/api_windows_service.py`
- `backend/src/libtv_agent/maintenance.py`
- `scripts/install-api-service.ps1`
- `docs/API_WINDOWS_SERVICE.md`
- `backend/tests/test_api_windows_service.py`

## 2. 已观察到的故障

管理员前台 debug 模式能够启动：

```text
Application startup complete.
Uvicorn running on http://127.0.0.1:8000
```

但执行 `Start-Service LibTVProductionApi` 后服务立即停止，PowerShell 只显示通用错误：

```text
Start-Service : 无法启动服务“LibTV Production API (Query Only) (LibTVProductionApi)”
```

Windows Application 事件日志中的真实异常为：

```text
Traceback ...
  File "...win32serviceutil.py", line 1062, in SvcRun
  File "...api_windows_service.py", line 125, in SvcDoRun
    asyncio.run(_serve(...))
  File "...asyncio/runners.py", line 189, in run
  ...
  File "...asyncio/windows_events.py", line 315, in __init__
    super().__init__(proactor)
ValueError: set_wakeup_fd only works in main thread of the main interpreter
```

结论：上述两次启动失败的直接原因是 pywin32 服务宿主下创建 Proactor 事件循环时调用 signal wakeup fd 失败。Selector 策略已修改，但尚未在真实 SCM 下验证；不能据此排除修复后出现其他独立问题。无需为这个异常继续扩大 ACL 或研究供应商合同。

## 3. 已完成的修复

提交：

- 测试分支 `codex/testing`：`41b877a fix: use selector loop in Windows API service`
- 生产分支 `main`：`3014b43 fix: use selector loop in Windows API service`

改动内容：

1. 新增 `configure_service_event_loop_policy()`。
2. 在 Windows 服务的 `SvcDoRun()` 调用 `asyncio.run()` 之前设置 `WindowsSelectorEventLoopPolicy`。
3. 增加 mock 回归测试，验证配置函数设置 Selector policy；该测试没有模拟真实 SCM 线程或宿主。

该修复只改变服务宿主的事件循环策略，不改变 API 路由、供应商逻辑、认证策略或生产数据。

## 4. 已完成验证

测试分支执行：

```powershell
& 'E:\Projects\libtv自动化生成\.venv\Scripts\python.exe' -m pytest backend/tests/test_api_windows_service.py -q
```

结果：`7 passed`。

源码工作树和生产同步工作树在交接时均无未提交修改。注意：自动化测试不等于真实 SCM 启动验证；必须重启 Windows Service 后再验收。

## 5. 当前 Windows 服务环境

已注册服务：

- 服务名：`LibTVProductionApi`
- 显示名：`LibTV Production API (Query Only)`
- 账户：`NT SERVICE\LibTVProductionApi`
- 数据根目录：`F:\Users\Reel\Documents\libtv-production`
- 监听地址：`127.0.0.1:8000`
- Python Service host：用户 AppData 下的 pywin32 `pythonservice.exe`
- 日志：`F:\Users\Reel\Documents\libtv-production\var\logs\api-service.log`

服务账户配置曾出现过两个已解决问题：

- `sc.exe` 传空密码导致配置失败；已改用 pywin32 `ChangeServiceConfig(..., password=None)`；
- 服务启动读取源码、Python 和运行目录曾需要管理员授予最小读取/执行或日志修改权限。

不要因为旧的 Access Denied 记录继续扩大 ACL。当前最新失败记录已经明确进入 Python 代码，并由事件循环异常退出。

## 6. 后续 agent 必做步骤

### 6.1 生产工作树确认修复存在

```powershell
Select-String -LiteralPath 'C:\Users\Reel\Documents\libtv-auto-main-sync\backend\src\libtv_agent\api_windows_service.py' -Pattern 'WindowsSelectorEventLoopPolicy|configure_service_event_loop_policy'
```

若找不到匹配，说明生产工作树未同步 `3014b43`，先同步代码再重启服务。

### 6.2 管理员重启并检查健康状态

```powershell
Restart-Service LibTVProductionApi
Get-Service LibTVProductionApi
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health/ready
```

预期：服务状态为 `Running`，健康检查 HTTP 200，响应显示数据库/schema 就绪。

### 6.3 如果仍失败，只读取新的服务事件

```powershell
Get-WinEvent -FilterHashtable @{
  LogName='Application'
  StartTime=(Get-Date).AddMinutes(-5)
} |
Where-Object { $_.ProviderName -eq 'LibTVProductionApi' } |
Select-Object TimeCreated, Id, Message |
Format-List
```

不要只依据 `Start-Service` 的通用错误判断根因。必须以该事件中的 traceback 为准。

本机曾出现 `Message` 为空、按 `ProviderName` 直接过滤报提供程序不存在的情况。此时保留上面的日志级过滤，再读取事件属性：

```powershell
Get-WinEvent -FilterHashtable @{
  LogName='Application'
  StartTime=(Get-Date).AddMinutes(-10)
} | Where-Object { $_.ProviderName -eq 'LibTVProductionApi' } |
ForEach-Object {
  $_.TimeCreated
  $_.Properties | ForEach-Object { $_.Value }
}
```

也可调用事件对象的 `.ToXml()` 查看原始 EventData。分享日志前检查是否含配置值或密钥。

### 6.5 工作树和测试隔离

- 测试源码：`E:\Projects\libtv自动化生成`，分支 `codex/testing`。
- 生产源码：`C:\Users\Reel\Documents\libtv-auto-main-sync`，分支 `main`，是独立仓库。
- 生产配置/数据：`F:\Users\Reel\Documents\libtv-production`，不是本次源码推广目标；其中已有用户修改，不要覆盖。
- 测试源码的 `var` 是指向生产数据的 junction。不要运行可能写入默认 `var`、加载真实 `.env` 或访问生产数据库的测试。
- 已有隔离运行器：`E:\Codex\visualizations\2026\09\23\01a0cdb7-c7c6-7840-ab2f-0c932e004dc2\G1\run_isolated.py`。先阅读其参数与隔离规则，再用于后续测试。
- 上述 7 项测试是在测试树直接运行的历史结果；尚无生产树同组测试或本次修复后的真实服务验收结果。
- 每次源码变更在测试分支验证后，再将对应提交推广到 `main`，保留生产差异。不得同步密钥、真实 `.env`、运行数据或缓存。
- 当前工具会话此前不具备管理员服务操作权限，管理员启动需由用户执行；不要绕过权限限制。
- 前端 5173 的后台托管是另一项任务。后端服务通过，不代表前端已长期托管或整个 G1 已验收。

### 6.4 维护模式验收

服务稳定后，验证：

- `GET /api/v1/health/live` 返回 200；
- `GET /api/v1/health/ready` 返回 200；
- 未认证请求按共享认证策略拒绝；
- 查询接口可用；
- 生成、确认、上传或其他写操作返回维护模式拒绝；
- 未启动 Runner、供应商轮询、下载或结算进程。

## 7. 不要做的事情

- 不要再次重复 `sc.exe config` 空密码命令；虚拟服务账户密码必须是 NULL。
- 不要把服务改回 LocalSystem 来绕过问题。
- 不要把整个用户目录或整个生产目录授予完全控制。
- 不要为了验收调用 Kling 付费 API、执行生产迁移或恢复 Runner。
- 不要把管理员 debug 模式当作 SCM 服务账户验收。
- 不要把 `127.0.0.1:8000` 称为正式前端入口；正式入口是 `http://192.168.30.126:5173/`。

## 8. 完成标准

只有同时满足以下条件，才可将本问题标记为完成：

1. `LibTVProductionApi` 在 SCM 下状态为 `Running`；
2. `127.0.0.1:8000/api/v1/health/ready` 返回 200；
3. 服务重启后仍能自动恢复；
4. query-only 保护和共享认证行为通过验证；
5. 没有启动 Runner 或任何付费供应商路径；
6. 测试分支和 `main` 均包含 `41b877a` 对应修复；
7. 新的事件日志中不再出现 `set_wakeup_fd` 异常。

---

## 9. 接手后验收结果（2026-09-25 15:41–15:47）

### 9.1 事件时间线修正

交接时两次失败（15:25:05、15:28:24）的 traceback 都指向 `api_windows_service.py:125`，而两棵树的修复提交（`41b877a` / `3014b43`）时间戳是 15:32:15。也就是说 **Selector 修复在真实 SCM 下从未被执行过**，那两次失败不能作为"修复无效"的证据。凡遇到"改了但现象没变"的服务问题，第一件事是核对 traceback 行号与当前源码是否对应。

### 9.2 第二层故障（新发现）

Selector 修复生效后 `set_wakeup_fd` 异常消失，随即暴露一个独立故障：

```text
File "...uvicorn/server.py", line 327, in capture_signals
  original_handlers = {sig: signal.signal(sig, self.handle_exit) for sig in HANDLED_SIGNALS}
ValueError: signal only works in main thread of the main interpreter
```

根因：pywin32 从 SCM 回调线程导入服务模块，`threading` 的首次导入发生在该线程，于是 `threading.main_thread()` 把回调线程当作主线程，uvicorn 内部那句 `threading` 守卫被绕过，直接调用 `signal.signal` 失败。修复：服务使用的 uvicorn Server 子类把 `capture_signals` 覆写为 no-op。

提交：

- `codex/testing`：`4cc99d4 fix: skip uvicorn signal capture in Windows API service`
- `main`：`58fb334 fix: skip uvicorn signal capture in Windows API service`

### 9.3 验收证据

| 检查项 | 结果 |
| --- | --- |
| 服务状态 | `Running`（PID 46472） |
| `GET /api/v1/health/live` | 200 `{"status":"ok"}` |
| `GET /api/v1/health/ready` | 200，`postgresql` / `databaseSchema` 均 ok |
| `Restart-Service` 后 | 重新 `Running`，健康检查 200 |
| `SvcStop` | 日志出现 `Application shutdown complete`，优雅退出 |
| 未认证 `GET /api/v1/auth/me`、`/api/v1/tasks` | 401 |
| 非白名单 GET、POST 写操作 | 503 `MAINTENANCE_QUERY_ONLY` |
| 服务进程子进程 | 无 |
| 事件日志中的 `set_wakeup_fd` / traceback | 不再出现 |

隔离测试：两棵树各 `9 passed`（原有 7 项 + 新增 2 项）。执行方式与第 6 条一致；测试器副本额外把 `tempfile.tempdir` 指向隔离目录，否则 pytest 捕获用的临时文件会被审计钩子拦下。

### 9.4 遗留建议（未实施）

`logging_config.configure_file_logging` 写入失败时返回 `None` 而不抛异常，`SvcDoRun` 也没有检查返回值。若日志目录对服务账户不可写，服务会照常启动但丢失全部诊断信息——正是这次故障最难排查的原因。建议后续在 `SvcDoRun` 中检查返回值，失败时调用 `servicemanager.LogErrorMsg`。本次验收确认文件日志写入正常（629 → 1141 字节），因此没有扩大改动范围。
