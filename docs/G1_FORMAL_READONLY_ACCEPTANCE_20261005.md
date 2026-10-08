# G1 正式版只读业务验收记录

日期：2026-10-05  
正式版入口：`http://192.168.30.126:5173/`  
范围：G1 正式版本只读业务验收和部署身份确认，不进入 G2。

## 1. 执行边界

本轮只执行 HTTP 只读检查和已登录浏览器页面浏览：

- 未创建任务、未确认方案、未上传素材、未生成图片或视频；
- 未执行审核、重试、恢复、下载、配置保存、账号管理或密码修改；
- 未启动 Runner，未调用付费 API，未执行迁移，未重启正式服务；
- 未读取真实 `.env`、生产数据库、生产 `var` 运行态或生产密钥。

正式版当前由响应头 `x-libtv-maintenance: query-only` 明确标记为查询模式。

## 2. Worktree 状态

验收开始与结束时两个 worktree 均保持干净：

| Worktree | 分支 | HEAD |
| --- | --- | --- |
| `E:\Projects\libtv自动化生成` | `codex/testing` | `cc762f6c8570328de2a0e06e0c30e24c5f4730f0` |
| `C:\Users\Reel\Documents\libtv-auto-main-sync` | `main` | `fffd8d409f42168df0de3feefac48cefb47995fa` |

本轮只新增本记录文档；文档先在 testing 验证，再同步到 main。没有推送远端。

## 3. API 只读结果

| 检查 | 结果 |
| --- | --- |
| `GET /api/v1/system/status` | 200 |
| `GET /api/v1/health/live` | 200，`status=ok` |
| `GET /api/v1/health/ready` | 200，PostgreSQL 和 schema 均 `ok` |
| 未认证 `GET /api/v1/auth/me` | 401 |
| 未认证 `GET /api/v1/tasks` | 401 |

`system/status` 关键字段：

```text
environment=development
sourceRevision=unknown
libtvAdapter=real
libtvExecutionMode=live
paidGenerationEnabled=true
paidGenerationAuthorized=true
```

Kling 状态为 `KLING_API_CONFIGURED_UNVERIFIED`，`available=false`。这表示凭据配置状态存在，但尚未通过官方只读任务查询验证；本轮没有触发验证。

## 4. 页面只读验收

已使用现有登录会话访问并读取以下页面，浏览器控制台未发现错误：

| 页面 | 只读结果 |
| --- | --- |
| 视频制作 | 页面正常渲染；处理中 0、已完成 0；生成按钮禁用；显示维护模式提示 |
| 图片中心 | 批量创作页正常；未上传素材；生成任务按钮禁用；生图记录为空 |
| 任务 | 全部 17；需要处理 11；生产中 0；已完成 0；失败 8 |
| 内容库 | 页面正常；通用动作、通用风格、品牌风格、品牌动作均为 0 |
| 管理中心 | 生产服务在线；运行、成员、Provider、流程与分析分区均可读取；写入/验证按钮禁用 |
| 设置 | 页面正常；个人偏好可读取；修改密码、偏好写入和通知设置均未执行 |

一条既有任务详情只读核对结果：任务整体为“待最终审核”，两个历史结果均显示“成品文件已就绪”，历史提示词快照和技术阶段信息可读取。未点击播放、下载、审核、恢复或重试操作。

## 5. 部署身份结论

当前不能证明正式 API 后端源码精确对应 testing 或 main：

- 正式 `system/status.sourceRevision` 返回 `unknown`；
- 响应未提供可用的 revision header；
- 正式 API 服务为 `LibTVProductionApi=Running`、`StartType=Automatic`，服务账户为 `NT SERVICE\LibTVProductionApi`；
- 启动脚本使用的后端源码指纹算法计算出 testing 与 main 不同，且两个分支存在历史源码差异；
- 正式前端当前由 Vite 进程提供，命令行路径指向 testing 工作区前端目录，但这不能替代后端部署身份确认。

因此本轮结论为：

> 正式服务在线，健康检查和查询型业务页面验收通过；正式后端部署 revision 未确认，不能宣称正式服务已精确同步到 testing 或 main。

### 5.1 2026-10-05 重启后部署身份确认

管理员重启正式 API 后重新确认部署身份：

- 服务 PID：`23864` -> `29468`；
- `sourceRevision`：`9d5a8775e9159e9b546d7f8e3aa5089c0bbe62c5f81cd0f9c4ffdb5acfe4d144`，与 `main` 当前源码指纹一致；
- `GET /api/v1/health/live`：200；
- `GET /api/v1/health/ready`：200，数据库和 schema 均正常；
- 未认证 `GET /api/v1/auth/me`：401；
- 未认证 `GET /api/v1/tasks`：401。

因此，前述 `sourceRevision=unknown` 是正式 API 重启前的观测结论，已被重启后的结果修正。正式 API 当前部署身份已确认与 `main` 指纹一致；本确认仍不改变正式版 query-only、Runner 未启动、未调用付费 API 的边界。

### 5.2 2026-10-08 生产迁移后只读确认

在取得明确授权后，使用 `main` 当前迁移链执行生产 SQLite 数据库升级：

- 迁移前 revision：`b7d9e1f3a502`；
- 迁移后 revision：`c9f0a1b2c304`；
- SQLite `PRAGMA integrity_check`：`ok`；
- 新增表确认：`product`、`product_version`、`image_quota_reservation`；
- 迁移前数据库副本已保存并通过完整性检查；
- 未重启正式 API，未启动 Runner，未调用付费 API。

迁移后正式版只读复核：

- `GET /api/v1/health/live`：200；
- `GET /api/v1/health/ready`：200，PostgreSQL 和 schema 均 `ok`；
- 未认证 `GET /api/v1/auth/me`：401；
- 未认证 `GET /api/v1/tasks`：401；
- 响应仍带有 `x-libtv-maintenance: query-only`。

因此，生产 schema readiness 阻塞已解除；正式版仍保持查询模式，不代表已授权或执行真实 Pilot。

## 6. 后续边界

若要让正式 API 暴露可靠的 `sourceRevision`，需要在 testing 先实现、测试并同步到 main；使该改动在正式版生效还需要用户明确授权正式 API 服务更新/重启。本轮不执行该操作，也不通过修改前端隐藏 `environment=development`。

G2（图片模板快照、批次清单和 ZIP 交付）不在本轮启动。
