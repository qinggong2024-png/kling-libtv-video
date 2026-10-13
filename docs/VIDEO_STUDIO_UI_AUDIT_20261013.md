# Video Studio 页面级 UI/UX 审查报告

日期：2026-10-13  
范围：`/studio/video`，仅覆盖 Design System + Video Studio  
审查分支：`codex/testing`  
本地入口：`http://127.0.0.1:5173/studio/video`  
正式入口：未部署、未重启、未执行正式版写入

## 审查方法与证据

本轮先读取 `PRODUCT_SPEC.md`、`DESIGN_SYSTEM.md`、`DEVELOPMENT_PLAN.md`、`QA_CHECKLIST.md`、`CHANGELOG.md` 和 `TECHNICAL_AUDIT_20261008.md`，再使用真实 Chromium/Edge 浏览器和隔离 Video Studio fixture 取证。fixture 只模拟 API，不调用 Provider、数据库、真实计费或生产服务。

截图和回归报告保存在工作区外：

`E:\Codex\visualizations\2026\10\13\01a1336e-9544-7550-b55e-6cc7657dcd4a\video-studio-audit-baseline`

`E:\Codex\visualizations\2026\10\13\01a1336e-9544-7550-b55e-6cc7657dcd4a\video-studio-audit-after`

状态覆盖了空状态、两张素材、七张素材、主体收起与展开、长文件名、模板切换、模板加载失败、自定义生成、自动生成、禁用提交、提交中、UNKNOWN、失败、批量校验、结果任务抽屉和结果播放。

## 结论

P0：无。

修复前页面的主要阻塞集中在 800–820px 中间宽度和提交反馈顺序。修复后，素材整理、创意配置、提交和结果保持同一纵向动线；移动导航与内部布局使用同一 821px 断点；提交前即可看到阻塞原因；七图仍自动换行；UNKNOWN 仍保持不可重提语义。testing 与 main 的最终隔离浏览器复跑均通过；此前 main 单次 768px 拖拽断言失败属于自动化复跑中的偶发失败，最终复跑未重现。

## P1

### P1-1：800–820px 外壳与内部布局使用不同断点

页面证据：修复前 `audit-two-long-800.png` 和 `audit-two-long-820.png` 显示底部移动导航已经出现，但生成配置和提交区仍使用桌面双栏/多列规则。代码中移动外壳从 820px 生效，而 Video Studio 内部桌面规则从 800px 生效，产生 800–820px 的断层。

用户影响：平板横向或窄桌面窗口同时看到移动导航和桌面提交结构，提交控件密度、滚动节奏和视觉锚点不一致；用户需要重新理解页面如何操作。

代码位置：`frontend/src/features/production/videoStudio.css:204`、`frontend/src/features/production/studioRefinement.css:131`、`:140`、`:163`。

局部修复：将 Video Studio 内部移动规则统一到 `max-width: 820px`，桌面素材排列和中间宽度提交规则统一从 `min-width: 821px` 生效。

验收标准：800×844 和 820×844 显示移动导航、单列生成配置、整行提交按钮；页面 `scrollWidth <= viewport width`；提交按钮滚动到可视区时不被固定导航覆盖。

修复证据：`video-studio-audit-after/post-two-800.png`、`post-two-820.png`；补测几何记录显示两种视口均为移动导航、提交按钮全宽、无横向溢出。

### P1-2：禁用提交原因出现在按钮之后

页面证据：修复前 `empty-1440.png`、`configured-success-1440.png` 和移动截图中，提交按钮先出现，“请至少上传 1 张分镜图”等阻塞原因位于提交区下方。

用户影响：首次用户看到不可用按钮后仍需向下寻找原因，无法立即建立“下一步该做什么”的判断。

代码位置：`frontend/src/features/production/ProductionComposer.tsx:569-592`。

局部修复：把 `.composer-feedback` 放到 `.composer-submit-row` 之前，保留原有 `role="alert"`、UNKNOWN、安全核对、模板失败和 Provider 状态语义。

验收标准：所有阻塞状态的解释出现在提交按钮之前；模板失败、自定义提示词缺失、素材数量不符、Provider 不可用和 UNKNOWN 均继续保留原有动作约束；提交成功、进行中和结果状态不误报为错误。

修复证据：`video-studio-audit-after/post-empty-800.png`、`post-two-800.png`；DOM 证据确认 `composer-feedback` 位于 `composer-submit-row` 之前。

### P1-3：移动端排序提示与真实能力不一致

页面证据：修复前素材缩略图 title 为“点击查看大图，长按拖拽排序”，但实现主要是 HTML `draggable`/`DragEvent`；移动端真实可验证的排序入口是每张素材下方的前移/后移按钮。

用户影响：用户会尝试长按拖动，失败后才发现需要使用箭头，造成操作不确定性。

代码位置：`frontend/src/features/production/MaterialCard.tsx:51`、`frontend/src/SubjectInputPanel.tsx:138`、`:222`。

局部修复：素材缩略图改为“使用左右箭头调整顺序”；主体参考图的桌面拖拽提示改为“拖拽交换位置（桌面端）”，不声称移动端支持直接拖拽。

验收标准：移动端提示只描述可用操作；排序、删除和大图检查仍在素材区内可达；桌面拖拽和键盘箭头回归通过。

修复证据：`video-studio-audit-after/seven-uploaded-390.png`、`post-two-360.png`；fixture 回归中的 pointer drag、前移/后移和删除均通过。

## P2

### P2-1：素材轨道有套卡视觉

页面证据：修复前 `seven-uploaded-390.png` 和 `configured-success-1440.png` 中，轨道整体有一层浅色背景，内部每张素材又有独立边界，形成外层容器加内层卡片的重复框架。

用户影响：素材整理任务被视觉包装成一个嵌套面板，缩略图和排序操作的主次关系变弱。

代码位置：`frontend/src/features/production/studioRefinement.css:49`。

局部修复：移除轨道整体背景和圆角，只保留素材缩略图、序号、删除和排序控件的局部边界。

验收标准：轨道仍能自动换行，单图单缩略图，七图无需横向滚动；空状态不产生轨道占位。

### P2-2：提交区与结果区阶段分隔偏弱

页面证据：修复前 `configured-success-1440.png` 中提交灰色区结束后，结果区主要依赖留白和标题，阶段变化不够明确。

用户影响：用户完成提交后不容易确认页面已经进入“等待/查看结果”的下一阶段。

代码位置：`frontend/src/features/production/studioRefinement.css:120`。

局部修复：为结果区增加 24px 上内距、32px 上外距和语义边界线，保留现有结果组件和真实状态。

验收标准：提交区和结果区之间有清晰的阶段边界；结果为空、进行中、失败和完成时都不依赖颜色单独传达状态。

### P2-3：中文页面出现英文拖拽提示

页面证据：修复前 `SubjectInputPanel.tsx` 使用 `title="Drag to swap positions"`。

用户影响：局部英文降低界面一致性，也没有说明移动端能力边界。

代码位置：`frontend/src/SubjectInputPanel.tsx:138`、`:222`。

局部修复：替换为中文且明确桌面端范围。

验收标准：Video Studio 页面不再出现该英文 title；中文提示与设备能力一致。

### P2-4：Video Studio 样式依赖两个 CSS 文件的导入顺序

页面证据：`ProductionComposer.tsx` 同时导入 `videoStudio.css` 和 `studioRefinement.css`，两个文件都定义 `.composer--studio`、`.composer-submit-row`、响应式断点和结果区规则。当前截图没有出现错误覆盖，但后续调整其中一个文件可能产生隐式回归。

用户影响：布局问题可能只在特定宽度或样式加载顺序下出现，维护成本和回归风险增加。

代码位置：`frontend/src/features/production/ProductionComposer.tsx:24-25`，对应两个 CSS 文件的同名选择器。

局部修复建议：后续单独整理 Video Studio 的样式层级或建立明确的 token/组件边界。本轮保留现有加载关系，避免扩大 CSS 重构范围。

验收标准：样式职责明确，改变一个文件不会无意覆盖另一个文件的页面级规则；补充 800、820 和 1102 宽度的回归。

## 视口验收

| 视口 | 结果 | 证据 |
| --- | --- | --- |
| 1440×900 | 通过 | `video-studio-audit-after/configured-success-1440.png` |
| 1102×884 | 通过 | `video-studio-audit-after/configured-success-1102.png` |
| 1024×768 | 通过 | `video-studio-audit-after/configured-success-1024.png` |
| 834×1112 | 通过 | `video-studio-audit-after/post-two-834.png` |
| 768×1024 | 通过 | `video-studio-audit-after-final/configured-success-768.png`；最终 testing/main fixture 均通过 `success-768` |
| 390×844 | 通过 | `video-studio-audit-after/configured-success-390.png` |
| 360×800 | 通过 | `video-studio-audit-after/post-two-360.png` |
| 800×844 | 通过 | `video-studio-audit-after/post-two-800.png` |
| 820×844 | 通过 | `video-studio-audit-after/post-two-820.png` |

## 仍未解决的问题与限制

- 移动端没有新增直接触摸拖拽排序；移动端使用每张素材的箭头排序，桌面端保留 HTML 拖拽。
- CSS 文件职责耦合仍存在，已记录为 P2 维护风险，未在本轮扩大为重构。
- 浏览器生成流程使用隔离 fixture，不能证明真实 Provider、真实费用、正式数据库或生产服务行为；最终 testing 与 main 各 13 个 fixture 用例通过。此前 main 一次 `success-768` 拖拽断言失败，随后在两侧最终复跑中均通过，保留为自动化稳定性观察项。
- 没有执行真实用户 5 分钟上手、3 分钟操作效率或生产质量收益测量。
- 本轮没有访问或修改正式版 `http://192.168.30.126:5173/`，没有部署正式版、重启服务、迁移数据库或调用付费 Provider。

## 本轮修改文件

- `frontend/src/features/production/ProductionComposer.tsx`
- `frontend/src/features/production/MaterialCard.tsx`
- `frontend/src/features/production/videoStudio.css`
- `frontend/src/features/production/studioRefinement.css`
- `frontend/src/SubjectInputPanel.tsx`

