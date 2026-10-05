# API 后台托管

`LibTVProductionApi` 是 Windows Service 入口，默认运行 `query-only` 维护 API：

- 支持认证、健康检查、系统状态和已有任务查询；
- 拒绝生成、确认、上传、供应商调用和其他写操作；
- 不执行 Alembic 迁移，不启动 Runner，不恢复后台付费任务；
- 日志写入 `var/logs/api-service.log`；
- 日志文件配置失败时，错误会通过 Windows SCM/Application 事件日志报告；
- 服务失败时由 SCM 自动重启。

## 预检

管理员 PowerShell：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\install-api-service.ps1 -Action Preflight
```

所有 Preflight/Install 命令必须额外传入 `-DataRoot 'F:\Users\Reel\Documents\libtv-production'`，源码工作树没有 Python 时额外传入 `-PythonPath 'E:\Projects\libtv自动化生成\.venv\Scripts\python.exe'`。服务将配置目录保存在注册表，不依赖终端临时环境变量；固定启用共享认证并绑定回环端口 8000。

预检只检查配置解析和 pywin32 导入，不验证数据库连接、服务账户权限或 SCM 实际启动。不会连接供应商，不会迁移数据库。

## 安装和操作

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\install-api-service.ps1 -Action Install
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\install-api-service.ps1 -Action Start
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\install-api-service.ps1 -Action Status
```

安装需要管理员权限。卸载使用 `-Action Uninstall`。安装前应确认 `8000` 没有其他 API 进程占用；不要同时运行前台 uvicorn 和该服务。

如果安装后账户仍显示 LocalSystem，说明安装只完成了注册而未完成账户配置。保持服务停止，在管理员 PowerShell 执行同一脚本的 `-Action Configure`，并用 `-PythonPath` 指定已安装 pywin32 的 Python，确认 StartName 为 `NT SERVICE\LibTVProductionApi` 后再处理目录权限。不要重复 Install，也不要使用 LocalSystem 绕过权限问题。虚拟服务账户要求 NULL 密码；脚本使用 pywin32 ChangeServiceConfig 传入 None，不经 sc.exe 转换空字符串。

服务账户为 `NT SERVICE\LibTVProductionApi`，安装后、启动前需由管理员授予源码、Python 和依赖目录读取/执行权限、正式 `.env` 与所需运行配置读取权限、日志目录修改权限。不要对整个生产目录授予完全控制。若凭据使用用户范围 DPAPI 加密，新服务账户可能无法解密；应先核实凭据机制，不复制或重置真实密钥。本脚本不自动修改生产 ACL、不安装依赖、不迁移数据库，也不自动启动服务。

服务已在 SCM 中安装，并于 2026-09-25 完成真实启动、重启和维护模式验收：状态 `Running`、`/api/v1/health/ready` 返回 200、`SvcStop` 优雅关闭、服务进程无子进程（未启动 Runner）、SCM 故障重启动作 5s/15s/60s 已配置。整机重启演练尚未执行，开机自启以服务 `Start` 类型 `Automatic` 为准。

后端不托管前端：服务只绑定回环 `8000`，不挂载 `StaticFiles`，前端进程消失与否都不影响它的启动和重启。前端目前由 `scripts\manage-frontend-host.ps1` 单独常驻在局域网 `5173`，详见 `docs/FRONTEND_HOST.md`。

前端目前仍是 Vite 开发服务器，适合局域网验收，不是长期正式静态托管方案。正式部署时应另行构建 `frontend/dist` 并交给 IIS/Nginx，不能让 Windows Service 托管 Vite 热更新进程。

## 已知启动故障与修复

服务宿主下出现过两层相互独立的崩溃。两者都必须以 Application 事件日志中 `Id=3` 的 traceback 为准，`Start-Service` 的通用错误没有诊断价值；事件 `Message` 可能为空，此时读取事件对象的 `Properties`。

1. **Proactor 事件循环**：`ValueError: set_wakeup_fd only works in main thread of the main interpreter`。pywin32 在服务线程中调用 `SvcDoRun`，默认 Proactor 策略会安装 signal wakeup fd。修复方式是在 `asyncio.run()` 之前切换到 `WindowsSelectorEventLoopPolicy`。
2. **uvicorn 信号捕获**：`ValueError: signal only works in main thread of the main interpreter`。pywin32 从 SCM 回调线程导入服务模块，`threading` 的首次导入就发生在该线程，于是 `threading.main_thread()` 把回调线程当作主线程——uvicorn `capture_signals` 里那句 `threading` 守卫因此被绕过，直接调用 `signal.signal` 失败。服务使用的 uvicorn Server 子类已把 `capture_signals` 覆写为 no-op；Windows 服务通过 SCM 停止（`SvcStop`），本就不需要进程信号。

排障时的第一件事是核对 traceback 的行号与生产工作树当前源码是否对应。行号对不上说明服务加载的不是当前代码，此时任何"修复无效"的结论都不成立。异常可能来自三层路径：pywin32 宿主、`api_windows_service.py` 宿主代码、uvicorn 内部。

`/api/v1/health/ready` 会通过 Alembic 只读检查 `alembic_version` 和迁移脚本头部，属于版本比对，不会执行 `upgrade`；日志中的 `alembic.runtime.migration Context impl SQLiteImpl.` 是正常输出。生产 `.env` 的 `DATABASE_URL` 指向 `sqlite+aiosqlite:///var/development.db`，因此该行显示 SQLite 而非 PostgreSQL，健康检查响应里的 `postgresql` 字段只是固定标签。
