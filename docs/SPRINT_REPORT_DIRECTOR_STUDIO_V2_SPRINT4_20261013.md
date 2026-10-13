# Sprint Report：Director Studio V2 Sprint 4

日期：2026-10-13
本轮范围：商品输入体验、中文阶段标题、前端创作意向记录和响应式对齐

## 完成

- 阶段导航、摘要和主标题采用“商品输入 / 创意方向 / 生产方案”；英文仅作为辅助标题。
- 保留“导演台”一个主产品标题；嵌入 Image Studio 时不再重复渲染外层标题，普通图片工作室标题及保存状态保持原样。
- 删除商品名称输入框，保留旧草稿字段以兼容恢复；原有任务命名和请求逻辑保持不变。
- 商品正面图、品牌归属明确标为已生效输入。
- 新增默认收起的高级创作设置，放在主按钮之后；包含产品材质、视频类型、模特性别、模特年龄范围、视频时长、视频比例和创作备注。
- 七项均为“计划支持”，明确说明不影响当前分析、创意方向或图片/视频 Prompt；不预设为已生效参数。
- 材质、视频类型、备注复用已有草稿字段；新增可选 `modelGender`、`modelAgeRange`、`videoDurationSeconds`、`videoAspectRatio`，只进入现有前端项目规划元数据。
- 修复阶段数字居中与标题对齐、商品输入标题/状态对齐及高级字段栅格；桌面沿用当前布局，移动端三个中文阶段完整同排。
- 390px 通用风格空状态和上传后状态的主按钮完整位于底部导航上方；上传图使用 contain，不裁切商品。
- 保持点击方向仅选择、确认才调用 `select_direction`、已确认锁定及原有生产方案内容/交互。

## 修改

源码和测试共十个文件：

- `frontend/src/features/director-studio/DirectorStudio.tsx`：标题、有效输入、折叠设置和中文提示。
- `frontend/src/features/director-studio/directorStudio.css`：步骤、标题、字段和移动端按钮布局。
- `frontend/src/features/image-studio/ImageStudio.tsx`：导演模式移除重复外层标题。
- `frontend/src/features/director-studio/contracts.ts`：可选前端规划字段。
- `frontend/src/features/director-studio/directorModel.ts`：可选 intake 字段，未改方向映射或状态规则。
- `frontend/src/features/director-studio/directorAdapters.ts`：规划字段到 Creative Brief 的映射。
- `frontend/src/features/director-studio/directorRecovery.ts`：复用现有恢复路径读取可选字段。
- `frontend/src/features/director-studio/directorRecovery.test.ts`：旧草稿兼容和规划字段持久化往返。
- `frontend/src/features/director-studio/DirectorStudio.browser-check.mjs`：高级输入、请求边界及原方向/生产流程回归。
- `scripts/ui-creative-shell-check.mjs`：V2 单阶段结构、唯一标题、移动端主按钮遮挡和普通图片工作室回归。

文档：`docs/CHANGELOG.md` 和本报告。

本轮提交没有修改后端、workflow、Agent、Provider、`directorApi.ts`、方向生成逻辑或生产包数据结构；生产阶段仅本地化主标题和空状态文案。

## 测试

- testing 原工作区 build、lint、Vitest 56 文件 / 398 项通过；当前并行工作保留，不把其他任务的改动计入本轮。
- 独立验证副本从 testing 的本轮提交 `d6de53f` 创建，build、lint、Vitest 56 文件 / 398 项再次通过；此副本不含并行任务的分析链路和后端新增能力。
- main 源码同步提交 `75bae5f`，独立 build、lint、Vitest 57 文件 / 394 项通过；保留两侧原有测试数量差异。
- 两侧隔离 Director 浏览器均通过 1440×900、1024×768、768×1024、390×844：默认折叠、七字段计划标签、清空时长、折叠保留内容和展开无横向溢出。
- 捕获任务创建表单，通用模式仍只有 `product_id`、`client_key`、`front`；analyze 命令仍只有 `action`、`command_key`、`expected_version`，没有计划设置。
- 各视口保留既有 18 个 Fake 命令回归：点击方向不生成包、确认仅一次调用、确认后不可切换、人工审核/刷新/首帧及分镜选择均通过。
- 两侧完整应用外壳浏览器均通过四视口和任务深链/列表返回；确认导演模式只有一个可见 h1、普通图片工作室标题正常。
- 390px 空状态和上传后状态检查主按钮完整边界位于移动导航上方，并使用 `elementFromPoint` 验证按钮中心没有被遮挡；不将仅位于视口内误判为可操作。
- testing 和 main 的 `npm run smoke:ui` 均在无代理、屏蔽写入的合成 GET 服务器上完成，9 个入口通过。
- Chrome 155.0.8059.39；截图已复核；没有真实 Provider 调用、数据库写入、正式后端联调或付费生成。
- testing 最终证据：`E:/Codex/director-v2-sprint4-isolated-testing-20261013`；testing smoke：`E:/Codex/director-v2-sprint4-smoke-testing-20261013`。
- main 最终证据：`E:/Codex/director-v2-sprint4-main-20261013`。
- 构建产物和浏览器证据保存在仓库外；main 的运行目录 dist 未覆盖，没有部署、服务重启或远程推送。

## 发现问题

- 七项高级设置尚未接入分析或 Prompt；本轮改善输入表达和界面真实性，不宣称生成质量提升。
- 既有恢复只在存在任务恢复引用时触发；单纯分析前的规划记录不保证刷新后自动回填，未扩大恢复行为。
- 本轮没有新增模特/时长/比例的 Provider 能力检查；所有选择都是意向记录，不承诺可执行性。
- 390px 首屏按钮验收针对默认通用风格及上传后的同一模式；已选品牌的完整 DNA 详情可能需要纵向滚动。
- 首轮新增分析请求断言漏计既有 `command_key`，已修正；没有改接口。
- 视觉复核发现主按钮被底部导航遮挡，新增严格遮挡断言并修复；上传后的文件名占位也单独验证。
- 完整页面脚本一次出现既有任务列表滚动恢复超时；保留原断言重跑及最终两侧独立验收通过，未改 Task Center。
- 工作区存在并行任务新增的 Director Analysis、后端和其他图片页面文件；本轮分离同文件的非本轮变更，只推广上述十个源码/测试文件及两份文档，未撤销并行工作。
- 同步只代表源码一致，不代表正式站点 `http://192.168.30.126:5173/` 已上线或通过真实生产验收。

## 下一步

- 人工确认商品输入层级、高级设置位置与“计划支持”说明是否清晰。
- 后续若批准高级设置生效，先定义真实请求合同、各字段用途和能力证据，再连接分析；本轮不做隐式接入。
