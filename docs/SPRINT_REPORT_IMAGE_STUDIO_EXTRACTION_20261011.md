# Sprint Report: ImageCenter to ImageStudio Extraction

日期：2026-10-11
分支：`codex/testing`
范围：Creative OS Frontend Migration Milestone 3

## Completion

- 将 ImageCenter 的运行实现迁移到 `frontend/src/features/image-studio/ImageStudio.tsx`。
- 新增 ImageStudio 公开合同模块和统一入口。
- 保留 `features/image-center/ImageCenter.tsx` 作为兼容导出层。
- 保留现有图片任务轮询、通知、审核、选择、恢复和图片到视频交接逻辑。

## File Changes

- `frontend/src/features/image-studio/ImageStudio.tsx`
  - ImageCenter 原有运行实现的新归属。
- `frontend/src/features/image-studio/contracts.ts`
  - ImageStudio props、handoff、notification 和视频主体来源合同。
- `frontend/src/features/image-studio/index.ts`
  - ImageStudio 统一公共入口。
- `frontend/src/features/image-center/ImageCenter.tsx`
  - 旧路径兼容层，保持历史导入和测试不变。
- `frontend/src/features/image-center/ImageCenter.test.tsx`
  - 验证 ImageStudio 抽取后的兼容导出。

## Contracts

- 未修改 `frontend/src/api.ts`。
- 未修改后端、OpenAPI、Provider、生成管线或任务状态。
- 未删除 ImageCenter。
- 未改变现有 query-view、task 深链接或 ImageCenter 无条件挂载约束。
- 未新增生产功能。

## Verification

- `npm run build`：PASS
- `npm run lint`：PASS
- `npm run test`：PASS，36 个测试文件、248 个测试
- 隔离 Playwright Director 检查：PASS，1440px 和 390px

## Findings and Limitations

- 本阶段是模块归属和兼容入口迁移，不是 ImageStudio 视觉重做。
- `imageReview.css` 暂时继续由 ImageStudio 引用原目录资源，避免 CSS 行为变化；后续可在单独清理阶段迁移样式文件。
- 后端 Creative Workflow 仍由独立窗口维护，前端未接入未冻结的真实 adapter。

## Next Step

Milestone 3 完成后停止，等待人工确认进入 Milestone 4：ProductionWorkspace → CreativeWorkspace shell。
