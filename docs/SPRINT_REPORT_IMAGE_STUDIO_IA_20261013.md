# Sprint Report：Image Studio 信息架构重构

日期：2026-10-13
范围：图片工作室前端入口层级与组件拆分；不修改后端 API、生成逻辑、任务状态模型或数据库。

## 完成

- 图片工作室默认首页改为创作任务选择页。
- 首屏一级入口固定为“图生图”“文生图”“批量生产”，顺序与使用频率一致，图生图排第一。
- “生图记录”保留为次级入口，不再与生产配置并列占据默认首屏。
- 当前复杂批量创作流程迁移到“批量生产”页面容器，原提交、轮询、审核、恢复和视频交接逻辑继续由 `ImageStudio` 运行时容器承载。
- 新增独立的首页、图生图、文生图、批量生产、记录组件，以及图片工作室 query 导航模块。
- 保留 `ImageStudio` 无条件挂载约束，避免离开页面后图片任务轮询和通知中断。

## 修改

- `frontend/src/features/image-studio/ImageStudio.tsx`
- `frontend/src/features/image-studio/ImageStudioHome.tsx`
- `frontend/src/features/image-studio/ImageToImageStudio.tsx`
- `frontend/src/features/image-studio/TextToImageStudio.tsx`
- `frontend/src/features/image-studio/BatchStudio.tsx`
- `frontend/src/features/image-studio/ImageRecords.tsx`
- `frontend/src/features/image-studio/imageStudioNavigation.ts`
- `frontend/src/styles.css`
- `frontend/src/features/image-studio/ImageStudio.browser-check.mjs`
- `frontend/src/features/image-studio/imageStudioNavigation.test.ts`

## 测试

- `frontend`: `npm run build` 通过。
- `frontend`: `npm run lint` 通过。
- `frontend`: Vitest 56 个测试文件、398 项通过；新增导航测试后将重跑并记录最终数量。
- 独立隔离浏览器检查：1440×900、1024×768、768×1024、390×844 全部通过。
- 浏览器检查覆盖：默认首页入口顺序、图生图、文生图、批量生产、记录、query 导航、浏览器后退、横向溢出和页面错误。
- 浏览器证据目录：`E:\Codex\image-studio-ia-evidence-testing`。
- 使用离线 fixture；没有真实 Provider 调用、付费生成、生产数据写入或正式版浏览器验收。

## 发现与限制

- 现有开发环境的 `/api` 连接异常仍是独立运行问题，本次没有修改代理、后端服务或 Windows 服务。
- 本次完成的是信息架构和入口层级调整，不代表图片生成质量、真实服务连通性或生产就绪状态已验收。

## 下一步

- 由产品负责人确认图生图优先的入口方向。
- 方向确认后，再分别补齐图生图和文生图的真实表单字段，并把现有批量配置继续作为专业生产工作区维护。
