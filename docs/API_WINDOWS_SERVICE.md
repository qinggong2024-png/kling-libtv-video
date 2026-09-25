# API 后台托管

`LibTVProductionApi` 是 Windows Service 入口，默认运行 `query-only` 维护 API：

- 支持认证、健康检查、系统状态和已有任务查询；
- 拒绝生成、确认、上传、供应商调用和其他写操作；
- 不执行 Alembic 迁移，不启动 Runner，不恢复后台付费任务；
- 日志写入 `var/logs/api-service.log`；
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

如果安装后账户仍显示 LocalSystem，说明安装只完成了注册而未完成账户配置。保持服务停止，在管理员 PowerShell 执行同一脚本的 `-Action Configure`，确认 StartName 为 `NT SERVICE\LibTVProductionApi` 后再处理目录权限。不要重复 Install，也不要使用 LocalSystem 绕过权限问题。Windows PowerShell 5.1 的空字符串原生命令参数可能丢失；脚本对 sc.exe 使用停止解析语法保留空密码参数。

服务账户为 `NT SERVICE\LibTVProductionApi`，安装后、启动前需由管理员授予源码、Python 和依赖目录读取/执行权限、正式 `.env` 与所需运行配置读取权限、日志目录修改权限。不要对整个生产目录授予完全控制。若凭据使用用户范围 DPAPI 加密，新服务账户可能无法解密；应先核实凭据机制，不复制或重置真实密钥。本脚本不自动修改生产 ACL、不安装依赖、不迁移数据库，也不自动启动服务。

当前交付为服务托管代码与隔离测试，尚未在 SCM 中安装或验证开机启动和故障重启。安装并完成健康检查前，不能关闭现有前台服务并宣称后台托管成功。

前端目前仍是 Vite 开发服务器，适合局域网验收，不是长期正式静态托管方案。正式部署时应另行构建 `frontend/dist` 并交给 IIS/Nginx，不能让 Windows Service 托管 Vite 热更新进程。
