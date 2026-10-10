# Sprint Report: Director Studio MVP

日期：2026-10-10
分支：`codex/testing`
范围：Creative OS Frontend Migration Milestone 2

## Completion

- 在现有 Image Studio / ImageCenter 内增加“智能导演”模式。
- 增加 Product Intake、Direction Candidates、DNA / Reality Summary 和 Production Package 规划界面。
- 方向选择写入 `CreativeProject` 的当前阶段和导演元数据；没有创建图片或视频任务。
- 保留现有 ImageCenter 的批量生图、结果审核、轮询、通知和图片到视频交接路径。
- 保留 `CreativeIntelligenceSnapshot` 作为只读显示接口；没有实现 Reality Engine、Spatial Understanding、Video DNA 或视频复刻。

## Changes

- `frontend/src/features/director-studio/directorModel.ts`
  - 规划阶段、商品输入、方向候选和选择动作的纯前端模型。
- `frontend/src/features/director-studio/DirectorStudio.tsx`
  - Director Studio MVP UI 和 Creative Project 适配。
- `frontend/src/features/director-studio/directorStudio.css`
  - 使用现有语义 token 的工作台布局和响应式样式。
- `frontend/src/features/director-studio/directorModel.test.ts`
  - 阶段初始化、候选选择和商品正面准入测试。
- `frontend/src/features/image-center/ImageCenter.tsx`
  - 新增页内模式入口；旧生产分支仍保留。
- `frontend/src/creative-project/hooks.ts`
  - 增加无 Provider 场景可用的可选上下文读取，以兼容现有离线 fixture。

## Contracts

- 未修改 `frontend/src/api.ts`、后端 API、生成 Provider、任务轮询和生产管线。
- 未新增路由；Director Studio 作为 Image Studio 内模式运行。
- 选择方向不等于生成授权，前端不会把规划数据显示为 AI 分析成功或正式交付结果。

## Tests

- `npm run build`：PASS
- `npm run lint`：PASS
- `npm run test`：PASS，36 个测试文件、247 个测试
- 隔离 Playwright 检查：PASS，1440px 和 390px；覆盖商品正面输入、方向选择、生产包锁定和未创建任务。

## Findings and limitations

- 后端 Creative Workflow 字段和错误码仍在独立窗口验收，因此当前 Director Studio 使用本地规划模型，不接入未冻结的真实 adapter。
- 生产包、DNA、Reality 和未来智能快照只显示边界状态，不生成或推断真实内容。
- 浏览器检查使用合成文件字节流，不代表真实图片 Provider 或后端生成质量验证。

## Next Step

Milestone 2 在前端规划范围完成后停止，等待人工确认。下一阶段为 ImageCenter 到 ImageStudio 的模块抽取。
