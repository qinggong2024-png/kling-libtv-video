# Sprint Report · Creative Workflow MVP-1C

日期：2026-10-11  
范围：Director Studio 规划模式接入现有 Creative Workflow 离线 API  
分支：`codex/testing`

## 完成

完成最小可用闭环：

```text
上传商品正面
→ 创建商品与离线 Creative Task
→ analyze
→ 选择 A / B / C
→ 授权 FIRST_FRAME
→ generate Fake 首帧
→ 展示任务状态与候选
```

页面明确标注“离线 Fake 模式 · 不可交付”。Fake 候选继续使用商品正面图作为占位，并显示 `OFFLINE_SYNTHETIC_ONLY`，不会显示为真实首帧、QUALIFIED 或 Deliverable。

## 修改

仅修改约定范围：

- `frontend/src/features/director-studio/DirectorStudio.tsx`
- `frontend/src/features/director-studio/directorModel.ts`
- `frontend/src/features/director-studio/directorApi.ts`
- `frontend/src/features/director-studio/directorModel.test.ts`
- `frontend/src/features/director-studio/directorApi.test.ts`
- 本报告

没有修改 `frontend/src/api.ts`、后端、迁移、OpenAPI、共享页面或服务。

`directorApi.ts` 复用现有 `getSystemStatus` / `getCurrentUser` 的身份上下文，在本模块内完成 Creative Workflow 请求适配；写操作继续发送 CSRF Cookie 对应请求头。请求沿用服务端 `state_version`，避免重复点击造成过期命令。

## 测试

- `npm run build`：通过
- `npm run lint`：通过
- `npm test`：通过，37 个测试文件、252 项测试
- Director 定向测试：2 个测试文件、7 项测试通过

## 发现问题

- 当前后端离线创建接口要求 `product_id`，前端因此先创建一个内部商品记录再上传正面图创建 Creative Task。内部 SKU 使用导演任务前缀和随机后缀，避免局域网多人使用时发生 SKU 冲突。
- 现有离线 Creative Workflow 接口没有接收品牌名称和创作备注的字段。本包保留页面输入，但不把它们伪装成已进入后端生产合同；后续若需要持久化，应另立后端合同包。
- Fake 结果没有可交付媒体地址，页面使用本地正面图预览候选。这只能证明任务、授权、生成和展示链路，不能证明真实像素质量、Provider 接收或生产资格。
- 未执行真实 Provider、付费调用、PostgreSQL、多 worker、生产迁移或正式版部署。

## 下一步

在内部 MVP 使用前，建议补一次隔离环境浏览器手测，确认测试服务处于 `app_env=test`、Fake/Replay、local object store、付费生成关闭状态。真实 Provider 首次接入另行授权，不与本包混合。
