# Sprint Report: Director and Image Workspace Separation

日期：2026-10-13
阶段：UI-2 / 工作区信息架构细化
范围：导航入口、图片工作室模式边界、导演台首屏文案、内容库首屏密度。

## 完成

- 导演台拥有独立的 Creative OS 导航入口，底层继续映射到现有 `view=images&pane=director`。
- 图片工作室只保留批量创作和生图记录两个工作区入口；导演台不再作为图片页内第三个模式标签。
- 导演台标题、状态和工作区壳与图片工作室区分，保留 ImageStudio 无条件挂载和后台轮询/通知行为。
- 导演台保留商品输入、方向选择、生产包、首帧、SHOT_01、Production Bridge、授权、审核、恢复和离线不可交付状态。
- 删除重复的 Brief 摘要展示，压缩不影响决策的重复说明；合同、阻断原因和证据仍由原有结构呈现。
- 内容库移除只读统计墙，保留分类、搜索、筛选、编辑和资源列表。
- 旧 `?view=images`、`?view=images&pane=director`、`?view=make`、`?task=id`、records 和 library 入口继续工作。

## 修改

- `frontend/src/app/App.tsx`
- `frontend/src/app/AppShell.tsx`
- `frontend/src/features/image-studio/ImageStudio.tsx`
- `frontend/src/features/director-studio/DirectorStudio.tsx`
- `frontend/src/features/library/ContentLibraryView.tsx`
- `frontend/src/styles.css`
- `scripts/ui-creative-shell-check.mjs`

## 测试

- `npm run build`：通过。
- `npm run lint`：通过。
- `npm run test`：322 项通过。
- 实际 `main`：build、lint、317 项测试通过。
- `npm run smoke:ui`：当前本地默认入口 root 为空，所有页面无法加载；属于现有运行环境缺口，不归因于本次代码。
- 隔离 Playwright 壳检查：1440×900、1024×768、768×1024、390×844 通过。
- 隔离 Playwright 任务深链接、详情关闭、records 滚动恢复通过。
- 隔离检查确认导演台导航独立选中，图片页没有重复“智能导演”模式按钮，ImageStudio 仍保持隐藏挂载。

证据目录：`E:/Codex/ui2-20261013-director-image-separation/`
main 证据目录：`E:/Codex/ui2-20261013-director-image-separation-main/`

## 同步

- testing：本轮前端/UI 文件已完成验证。
- main：同一局部改动已同步并独立验证通过。
- 未同步 `.env`、构建产物、缓存或其他窗口的未提交业务文件。

## 发现问题

- 默认 `npm run smoke:ui` 连接的 `127.0.0.1` 实例当前返回空 root，不能作为本轮页面验收证据。
- Impeccable detector 报告了既有全局样式中的边框、字体和动效建议；本轮新增样式未引入新的生产逻辑或状态表现。

## 下一步

- 在人工体验确认后，继续按真实操作频率细化 Director Studio 与 Image Studio 的候选、证据和结果区。
- 不进入真实 Provider、生产数据写入或 Creative Workflow 数据模型调整。
