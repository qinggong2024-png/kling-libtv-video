# Sprint Report：正式服务恢复

日期：2026-10-14
范围：恢复正式入口、修复宿主启动、验证现有开机恢复配置和记录后续部署准备。

## 完成

- 正式入口 `http://192.168.30.126:5173/` 恢复，前端监听 0.0.0.0:5173。
- API 运行在 `LibTVProductionApi`，回环 8000，虚拟服务账户。
- 正式 SYSTEM 计划任务 Running，boot 和每分钟重复触发，不依赖交互登录。
- API Auto + 延迟启动、SCM 5s/15s/60s 恢复；前端不限运行时长、999 次失败重试。

## 修改

- testing/main 的 Node 路径解析过滤空 PATH 项及无法组合的路径。
- 等待 Node 版本命令结束后再取首行，避免管道提前结束产生 -1 退出码、误判健康 Node。
- 动作分发记录未捕获异常后抛出，隐蔽任务不再只留下启动标题。
- main 采用 testing 已有的监督等待心跳和重复启动拒绝状态说明；Vite 输出阻塞时仍以 HTTP 为准。
- 新增不启动服务器的回归脚本，并更新 FRONTEND_HOST、API_WINDOWS_SERVICE 和 CHANGELOG。
- 运行时修复：恢复服务实际基础 Python 的 pywin32.pth，未将该文件提交或跨分支同步。

## 测试

- Windows PowerShell 5.1：testing/main 语法检查、显式/自动 Node 解析含空项 PATH、早期失败日志检查通过。
- 正式首页 HTTP 200；浏览器呈现账号登录页，读取控制台未发现 warn/error。未登录、未提交业务操作。
- 正式代理 `/api/v1/health/live`、`/api/v1/health/ready` 和 `/api/v1/system/status` 均 200。
- 回环 API live/ready 均 200，ready 包含数据库/schema 检查通过；响应维持 query-only。
- SYSTEM 注册表 PATH 的空项数为 1；修复后 10:35 的自动触发成功启动 Node/Vite。
- 已核对任务宿主父进程仍存在；本轮未主动终止 SYSTEM 进程做崩溃演练。
- 两侧只同步本轮源代码、回归脚本和文档，保留分支既有差异及用户未跟踪文件。
- 未改前端页面或业务代码，本轮不重复完整前端 build/lint/单测或声称产品流程重新验收。

## 发现问题

- API 原失败源于实际 pythonservice 基础运行时缺少 pywin32 路径文件，项目 venv 预检不足以证明 SCM 能启动。
- SYSTEM 空 PATH 项使原前端解析器在检查显式 Node 前抛错，任务失败每分钟重复。
- 正式目录回归发现原版本探测管道会提前停止 Node；已修复后重跑两侧检查。
- 非管理员读 SYSTEM 进程无法取得命令行，Status 的 OwnedByWorkspace 可为 False；结合任务 Action、日志及父进程确认托管归属。
- 旧 Local Stack Watchdog 已禁用，继续保持禁用，避免触发迁移、Runner 或抢占 API 端口。
- 当前前端仍使用 Vite，当前服务仍是 query-only；健康通过不等于已开放全部生产业务。
- 普通 Install 是交互用户登录任务，不能覆盖当前 SYSTEM boot 任务。

## 下一步

- 维护窗口执行真正的整机重启和异常恢复演练，验证无需登录即可恢复及数据盘就绪时间。
- 当前电脑关机、休眠或断电会停止访问；开机自动恢复不等于关机期间可用。
- 长期目标为常开服务器：静态前端 + API 反向代理、独立运行数据/数据库和备份，
  安全交付运行凭据，目标机健康/登录/重启验收后切换正式入口。
- 尚未提供并配置常开目标主机，因此未声称已完成脱离此电脑的迁移。
