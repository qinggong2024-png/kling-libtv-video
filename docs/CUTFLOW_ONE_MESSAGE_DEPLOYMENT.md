# Cutflow 单次发送部署指令

日期：2026-10-14。用途：将同一份完整执行任务发给 Cutflow 电脑上的
Codex/管理员，完成现有 Bridge 部署及节点验收，不重新开发。

这是一份部署执行指令，不是保证成功的通用 shell 命令。
当前两端存在真实阻塞，不能用一句命令保证服务构建、NAS 权限、
母版兼容和人工质量。单次发送可以减少往返，不取消必要的阻塞报告。

## 发送给 Cutflow 端

以下整段作为一次消息发送给 Cutflow 电脑上的 Codex。
它必须在真实 Cutflow 电脑执行；此处的右侧网页登录不能代替远程终端。
发送这段指令意味着允许下述 Cutflow 部署/配置及按现有流程重启；
发送前由操作者确认具有相应权限。衣影工坊迁移仍单独授权。

```text
请完成 Cutflow 现有 LibTV Bridge 部署并验收执行节点。
这不是功能开发任务，不修改架构或新增 API。

已知地址：
Cutflow LAN：http://192.168.30.35:3001/
衣影工坊：http://192.168.30.126:5173/
NAS 根目录：\\192.168.120.60\新成片交付\批量剪辑素材
部署包：该 NAS 根目录下 test\cutflow-bridge-deployment-20261014

本次允许：
- 核查真实运行环境；
- 应用部署包中已完成的 Bridge 文件；
- 备份并配置 Bridge 环境项；
- 验证构建后按原有方式重建/重启 Cutflow Web 服务；
- 按原有运行账号和托管方式启用一个 Bridge worker。

禁止：
- 重写架构、另做功能、覆盖整个仓库、清空 data/storage；
- 强制覆盖远程差异、创建用户或改变母版归属；
- 自动生成付费视频、创建演示/伪造批次、重新调用付费分析；
- 迁移衣影工坊数据库或重启衣影工坊服务；
- 在报告、聊天或 NAS 部署包中保存真实 token、密码或 .env。

按顺序执行，独立核查可继续，失败阶段不反复提交、不转成开发：

1. 找到监听 3001 的实际代码目录、运行账号、启动/托管方式。
   不把默认路径或历史模板路径当成实际运行目录。
   检查有无在运行批次，避免中断其他人的生产。

2. 读取部署包 manifest.json，逐文件验证 SHA-256；
   对比已有 atomic-json.mjs、tenant-paths.mjs、task-number.mjs，
   确认导出函数和行为与 Bridge 兼容。
   包中 hash 是被审查版本的证据，不允许通过覆盖依赖消除差异。
   检查 Bridge 模块、两条 route、worker 的远程当前内容。

3. 保存本地备份和变更清单，先检查完整 patch 是否适用；
   远程文件缺失时安装对应 payload；同内容时跳过；
   存在不同内容时停止应用并报告差异，不能强制覆盖。
   不复制 .env.example 的占位值替换真实配置。
   保留其他开发改动、Provider 配置、账号、素材和运行数据。

4. 用实际 Cutflow 执行账号在 NAS 的 test 目录创建唯一探测文件，
   读取核对并记录 hash、大小，删除该唯一文件。
   确认服务账号与桌面账号的权限差异；若 worker 以另一账号运行也要核查。
   若为衣影工坊端互读验证留文件，明确路径并保留到对端确认再清理。

5. 只读取 data/users.json 的必要账号字段，不输出密码 hash 等敏感字段。
   核实 REEL 对应的活跃 owner UUID。
   从 data/templates.json 核实 ready、profile 和 ownerId。
   网页显示公共母版不等于属于当前 owner；
   不通过转移归属、虚构镜头或复制素材凑过验收。
   返回可用于该 owner 的母版名称与 UUID，未匹配就准确报告。

6. 只在本机安全配置以下环境项：
   LIBTV_BRIDGE_ENABLED=true
   LIBTV_BRIDGE_ROOT=\\192.168.120.60\新成片交付\批量剪辑素材
   LIBTV_BRIDGE_TOKEN=两端相同的独立服务凭证
   LIBTV_BRIDGE_OWNER_MAP=真实LibTV用户UUID到Cutflow owner和templateId的映射
   映射初次使用 autoQueue=false；核实后才启动现有剪辑流程。
   UUID 未获得时先列出候选，不填假值、不用共享账号替代映射。
   真实凭证通过操作者的安全方式在两端本地填写，不发给聊天、不放共享NAS。
   确认 Web 和 worker 都加载同一配置，环境变量覆盖也要检查。

7. 执行针对 Bridge 的测试、类型检查和必要的 Web 构建；
   保留现有工具链，不为了构建另升级框架或依赖。
   如果既有完整构建失败，记录原因，不能把局部测试通过写成部署成功。
   构建成功且配置齐备后按现有服务托管方式重启 Web，
   再启用一个 Bridge worker，不重复启动原 analyze/clip/render 服务。
   Node worker 从实际项目根目录运行，并显式加载私有环境文件。
   不在不确定的旧队列上试跑 --once，它可能处理其他用户待办。

8. 验证 LAN 路由：
   无凭证 POST /api/integrations/libtv 应被拒绝，不能返回 HTML 404。
   有效服务凭证配空 descriptor 应被拒绝且不产生 receipt/batch。
   不伪造正式 handoffId 创建批次。
   核查 Bridge worker 进程/日志，而非仅看普通 Worker 在线。
   页面上 Codex 当前“需要重新连接 / Model Service 未知”，
   记录真实原因；没有付费授权时不运行计费模型探针。

9. 脱敏报告写到 NAS：
   test\cutflow-bridge-deployment-20261014\CUTFLOW_NODE_DEPLOYMENT_RESULT.md
   包含实际目录、版本、运行账号、变更/备份清单、测试结果、
   route HTTP 状态、NAS 文件测试、owner UUID、可用 templateId、
   token 是否设置（绝不输出值）、worker 状态、具体阻塞。
   区分 FILES_INSTALLED、CONFIGURED、SERVICE_READY 和 BLOCKED；
   缺 userId/token/template 或服务没重启时不能写 SERVICE_READY。

10. 此任务到节点就绪为止，不自行创建真实剪辑批次。
    衣影工坊端随后完成经授权的迁移、维护模式切换和同一凭证配置。
    两端均就绪后由衣影工坊提交唯一真实 handoff：
    一个用户、一个产品、一个已有AI视频、一个匹配母版。
    原视频不替换，回传结果显示独立“待审核版本”。
    失败只定位阻塞，不新增功能或额外付费尝试。
```

## 衣影工坊侧接续

远端报告回到 NAS 后，本机继续既有任务，不需要复制远程运行目录：

1. 读取远端脱敏报告，核实 owner/mother template 与选定真实视频。
2. 两端用同一安全凭证；配置
   `CUTFLOW_BASE_URL=http://192.168.30.35:3001` 和真实 UNC。
3. 核对当前全部迁移链、数据库备份、API 切换方案及 worker 运行账号。
   2026-10-14 14:30 的健康请求已期望 `c8e9f0a1b2c3`；
   不把旧 Cutflow head 当作当前全部 schema，不直接全量升级。
4. 当前用户要求未授权自动迁移；提交具体操作范围再执行。
5. 两端 ready 后只创建一条真实交接，采集各阶段证据；人工观看由人确认。

当前缺 LibTV 测试 user/artifact、真实 owner/template 绑定、两端服务 token、
远端启动方法和本机迁移授权。因此部署包准备成功不等于视频闭环成功。

## 包内容与验证

`payload` 只包含已完成 Bridge 的 8 个源码/测试/说明文件，
外加完整 patch、逐文件 SHA-256、依赖基线 hash、本文和已核查部署报告。
不含真实 `.env`、token、users/templates 数据或视频。

生成命令从 testing 项目运行，OutputDirectory 必须是新目录：

```powershell
.\scripts\package-cutflow-bridge.ps1 `
  -SourceRoot 'E:\Codex\cut-architecture-v2-review' `
  -PatchPath 'E:\Codex\validation\cutflow-20261014\cutflow-libtv-bridge.patch' `
  -OutputDirectory '\\192.168.120.60\新成片交付\批量剪辑素材\test\cutflow-bridge-deployment-20261014'
```

该命令只生成部署包，不安装或启动服务。本次在生成前先执行包内 Bridge
既有离线测试，生成后逐项核对 payload 与 manifest。远端真实构建、部署、
服务账号权限和成片质量仍须分别验收。
