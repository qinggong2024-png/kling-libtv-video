# Sprint Report: Creative Core / Sprint 3 Human Review

日期：2026-10-13
状态：testing 与实际 main 源码同步完成；工程验收通过，未部署。

## 完成

- 图片与导演候选支持 PASS / REWORK / FAIL，视频支持 PASS / FAIL。
- 图片原因：FACE / GARMENT / REALISM / SPACE / LIGHTING / OTHER；
  视频原因：MOTION / DEFORMATION / CAMERA / OTHER。
- PASS 不接受失败原因；负向结论必须有原因，OTHER 必须填写说明。
- 使用已有 AuditEvent 追加保存评价、审核人、时间、输出 hash、任务和可用包来源。
- 使用已有 ApiIdempotencyRecord；审计和幂等结果在同一事务内提交。
- 结果不确定时保存原请求键与完整请求；刷新核对历史或重试同一请求。
- 历史、提交与导出只允许访问自有素材；auditor 保持只读。
- 默认导出排除 Fake/Replay 和持久化合成来源；不触发训练或自动学习。
- PASS 不改变 QUALIFIED、最终批准、交付、费用或执行状态。

## 修改

- 新增 creative/human_review.py、services/human_reviews.py 和 api/human_reviews.py。
- 注册 GET/POST /api/v1/human-reviews 和 GET /api/v1/human-reviews/export。
- 新增独立 HumanReviewPanel、输入校验及 pending 恢复模型。
- 在图片审核抽屉、已有视频结果和导演首帧/分镜候选作窄范围挂载。
- 增加后端合同/事务/权限回归、前端恢复测试及真实评价 API 浏览器检查。
- 复用旧存储，无 ORM 变更、迁移、State 扩展、Provider 重构或生产配置变更。

## 测试

- 后端专项 78 项通过，包含并发单记录、响应丢失后重放、冲突、事务回滚、
  越权、来源绑定、损坏审计拒绝、最新可用视频和合成数据过滤。
- 真实应用 ASGI 检查通过：路由注册、session 认证、伪造身份头无效、
  CSRF 拒绝/放行及 no-store；不启动生产后台 workers。
- testing 后端两组分别 157 / 128 项通过；共享 78 项专项，未作为互斥统计。
- main 独立后端组合 207 项通过；两侧专项 Ruff 通过。
- testing 前端 55 文件 / 393 项；main 56 文件 / 389 项通过。
- 两侧 lint、TypeScript、外部目录 build 通过，保留原有测试及源码差异。
- 两侧真实评价 API + 隔离 SQLite 浏览器 1440/1024/768/390 通过：
  三态/两态、OTHER 必填、历史刷新、导出排除合成记录、无横向溢出。
- 两侧浏览器确认：已提交但响应丢失后恢复只保留一条记录；未提交成功时
  重试沿用完全相同的键与请求；只读、明确拒绝、存储不可用均正确处理。
- 截图复核桌面/移动布局；评价历史统一按时间倒序展示。
- 证据目录：E:/Codex/verification/human-review；构建及数据库均在仓库外。

## 发现问题

- 修复 pending 哈希接受数组隐式转换的问题，并保留回归用例。
- 修复历史读取与保存可同时发起，以及新评价与重载历史顺序不一致的问题。
- 测试不依赖未声明 jsdom，使用 Node 内存 Storage；真实 DOM 由浏览器验收。
- Director 缺包时包元数据如实为 null，不借用其他包。
- 视频绑定最新可用 READY 工件，不保证最新 attempt 已成功。
- 现有幂等记录有效期为 90 天；删除或过期清理后不承诺永久去重。
- AuditEvent 为应用层追加记录，不宣称数据库具备防篡改不可变触发器。
- 未验证 PostgreSQL 多进程并发、长期数据规模及真实媒体像素质量。
- 正式前端 http://192.168.30.126:5173/ 本轮只读探测拒绝连接；
  未部署、重启、付费调用、生产数据写入或迁移。

## 下一步

- Sprint 4 对合成球衣执行上传、Brand DNA、三方向、选方向、Package、
  旧图片记录和人工评价的整合验收，分别记录通过项与真实链路缺口。
- 真实产品理解与图片/视频实产保持待验，不将 Fake 成功提升为完整生产交付。
- 若需解除离线闸或改变真实账本/生产流程，按用户要求先提交具体边界决策。
