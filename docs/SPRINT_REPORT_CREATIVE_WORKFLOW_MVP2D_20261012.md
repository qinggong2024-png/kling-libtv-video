# Sprint Report: Creative Workflow MVP-2D

日期：2026-10-12  
范围：包 B：Director 任务恢复  
分支：`codex/testing`

## 完成

- 使用版本化 `localStorage` 保存 `creative_task_id`、商品/商品版本/源哈希引用和规划快照索引。
- Provider 自动恢复和持久化 CreativeProject；清理时不保留导演任务引用。
- Director 重新进入页面时优先 GET 服务端任务，恢复审核、选择和规划状态。
- 浏览器 `File` 仅用于当前会话上传，不作为持久化真源。
- GET 返回任务不存在、归属/引用错误、商品版本过期或源引用失效时清理本地引用；网络失败保留引用并提示重试。
- 未修改后端 schema、数据库迁移、真实 Provider 或旧生产组件。

## 修改

- `frontend/src/creative-project/types.ts`
- `frontend/src/creative-project/store.ts`
- `frontend/src/creative-project/provider.tsx`
- `frontend/src/creative-project/recovery.ts`
- `frontend/src/features/director-studio/DirectorStudio.tsx`
- `frontend/src/features/director-studio/directorApi.ts`
- `frontend/src/features/director-studio/directorSelectors.ts`
- `frontend/src/features/director-studio/directorRecovery.ts`
- `frontend/src/features/director-studio/directorRecovery.test.ts`

## 测试

- Scoped Vitest：通过，5 个既有相关测试文件，14 项。
- Recovery helper Vitest：本轮新增，覆盖 localStorage、File 排除、GET 快照校验、商品版本过期和错误分类。
- `npm run build`：通过。
- `npm run lint`：通过。

## 发现问题

- 当前产品仍是离线 Fake/Replay 范围；恢复成功不代表真实 Provider 或交付资格。
- 恢复后的商品图没有浏览器 `File`，页面显示服务端引用提示，真实缩略图继续由后续生产桥接负责。
- 本轮未执行真实服务、浏览器刷新流程、数据库迁移或 Provider 调用。

## 下一步

- 待后续批准后接入包 A 的 `director_fixed` 入口和离线浏览器恢复验收。
