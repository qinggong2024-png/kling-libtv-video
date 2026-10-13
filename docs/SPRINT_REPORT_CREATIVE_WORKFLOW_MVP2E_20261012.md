# Sprint Report：导演入口接线与任务恢复

日期：2026-10-12  
范围：包 A `director_fixed` 离线入口、包 B Director 任务恢复，以及证据展示补齐  
状态：离线 MVP 功能完成，真实 Provider 仍后置

## 完成

- 将导演规划快照适配为版本化 `director-fixed-offline.v1` 只读输入。
- 在 Video Studio 显示 `creative_task_id`、package revision、`SHOT_01`、候选 ID、源图哈希和 shot mapping。
- 保留旧 automatic/custom、RemixSeed 和真实视频提交路径；导演入口不上传、不创建任务、不调用 Provider。
- 以 `localStorage` 持久保存导演任务引用、商品/版本/源哈希和规划快照索引。
- 页面重新进入时优先 GET 服务端任务；恢复审核、选择和当前版本。
- 任务不存在、owner 不匹配、商品版本过期或源引用失效时清理本地引用并提示；网络失败保留引用。
- 不持久化浏览器 `File`，不新增后端 schema、迁移或生产提交语义。
- 增加 Canonical Product、背面假设、Grounded Claims、Reality 六维和 Prompt/Preservation 摘要展示，并明确 `UNVERIFIED`/`OFFLINE_SYNTHETIC_ONLY`。

## 修改范围

- `frontend/src/creative-project/`
- `frontend/src/features/director-studio/`
- `frontend/src/features/production/`
- `frontend/src/features/task-center/HomeView.tsx`
- `docs/SPRINT_REPORT_CREATIVE_WORKFLOW_MVP2D_20261012.md`

主分支保留其已有 Reality Engine 类型和 SubjectInputPanel 重载能力，做了兼容适配；没有覆盖生产专属差异。

## 测试

testing：

- Vitest：44 个测试文件，279 项通过。
- ESLint：通过。
- TypeScript/Vite build：通过。
- 目标桥接、恢复、证据和 Composer 测试：11 项通过。

main：

- Vitest：47 个测试文件，282 项通过。
- ESLint：通过。
- TypeScript/Vite build：通过。
- 目标文件 SHA-256 与 testing 对应实现一致；主分支额外保留 Reality Engine 兼容层。

## 限制

- 尚未执行真实 Provider、付费生成、生产数据库迁移、服务重启或正式部署。
- 尚未进行正式版 `http://192.168.30.126:5173/` 浏览器验收。
- Fake/Replay 仍是 `OFFLINE_SYNTHETIC_ONLY`，不具备普通 QUALIFIED、生产或 Deliverable 资格。
- `director_fixed` 当前完成的是离线入口和只读 preflight，不是实际视频执行。

## 下一步

进入离线整体验证阶段：先做刷新/离开再进入和 Video Studio 导演准备区的浏览器流程验证；完成后再由业务负责人决定是否批准真实 Provider 单样本验证。
