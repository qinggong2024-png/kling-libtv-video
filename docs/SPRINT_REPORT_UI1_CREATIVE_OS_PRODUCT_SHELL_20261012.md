# Sprint Report：Creative OS Product Shell Design

日期：2026-10-12
阶段：Milestone UI-1
分支：`codex/testing`

## 完成

- 建立 Creative OS 产品导航层：工作区、项目、导演、图片、视频、审核、资产、记忆。
- 保留既有操作导航：图片中心、视频制作、任务、内容库、管理、设置。
- 建立 Creative Workspace 当前项目入口，展示项目状态、创意概览、生产路径和下一步操作。
- 将 Director、Image、Video、Review、Assets、Memory 映射到既有页面和能力边界。
- 统一 Creative OS 状态徽标、面板、生产路径、审核提示和下一步操作的基础样式。
- 保留 `ImageStudio` 无条件挂载，继续支持后台轮询、通知和已有图片任务恢复。
- 为 Director surface 增加 UI-only 初始模式入口，未修改图片生产逻辑。
- 增加产品 surface、旧链接兼容和 Creative Workspace 展示模型测试。

## 修改

- `frontend/src/app/App.tsx`
  - 接入 Creative OS product navigation。
  - 接入 Creative Workspace、项目上下文条和 surface 分发。
  - 保持旧 `view` 与 `task` 分发。
  - Creative Workspace surface 下隐藏旧 Video Studio 主内容，避免页面叠加。
- `frontend/src/app/AppShell.tsx`
  - 增加产品导航、旧操作导航分组和移动端产品导航。
  - 增加当前项目上下文区域。
- `frontend/src/app/productNavigation.ts`
  - 定义 surface 到既有 view 的映射和 project query 保留规则。
- `frontend/src/app/useAppNavigation.ts`
  - 支持 surface 导航、浏览器历史和旧链接兼容。
- `frontend/src/features/creative-workspace/*`
  - 增加工作区展示模型、状态映射、生产路径、项目页和 Creative Memory 当前项目视图。
- `frontend/src/features/image-studio/contracts.ts`
  - 增加 `initialMode` UI 参数。
- `frontend/src/features/image-studio/ImageStudio.tsx`
  - 响应 Director / Image surface 的初始模式。
- `frontend/src/shared/components/studio/CreativeFoundation.tsx`
  - 提供 Creative OS 状态、面板、步骤和审核摘要基础组件。
- `frontend/src/styles.css`
  - 增加产品壳、项目上下文、工作区、步骤路径和移动端响应式样式。

没有修改 `frontend/src/api.ts`、Backend API、Task State Model、Provider、Production Pipeline、Billing、quota 或 ledger。

## 测试

- `npm run build`：通过。
- `npm run lint`：通过。
- `npm run test`：通过，52 个测试文件 / 319 个测试。
- 浏览器只读验证：使用本地 Vite `http://127.0.0.1:5174/` 与 Chrome。
  - Desktop：1440 × 900。
  - Laptop：1024 × 768。
  - Mobile：390 × 844。
  - 三种 viewport 均可显示 Creative Workspace，无横向溢出。
  - Mobile 显示横向 Creative OS 产品导航。
  - Product surface 点击、URL 写入、back / forward 通过。
  - `?view=images`、`?view=make`、`?view=records`、`?view=library`、`?task=id` 继续进入既有页面分发。

## 发现问题

- 本地 backend 未连接时，Vite `/api` 代理返回 `502 Bad Gateway`，页面显示既有服务异常提示。该结果属于运行环境限制，不是本阶段前端编译或路由异常。
- 浏览器验证未执行真实生成、真实 Provider 提交或生产数据写入。
- 当前项目仍是本地 Creative Project；项目列表没有新增后端数据模型或项目管理 API。
- Product surface 当前是产品体验层映射，未替换既有 `?view` 合同。

## 下一步

- 停止在 Milestone UI-1，等待人工确认产品壳、信息架构和操作动线。
- UI-2 再处理高保真视觉、动效和空间细化。
- 进入 UI-2 前不扩展真实 Provider、AI Intelligence 或生产桥接逻辑。
