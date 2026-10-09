# 衣影工坊 V1 QA Checklist

版本：V1.0
日期：2026-10-08
状态：开发与交付验收标准冻结

## 1. 自动化门禁

每次前端变更至少执行：

```powershell
cd frontend
npm run build
npm run lint
npm run test
```

涉及页面交互时追加：

```powershell
npm run smoke:ui
```

上述 npm 脚本均在 `frontend` 目录运行。UI smoke 需要显式指定已授权的测试入口；默认 localhost 不是正式版。现有 smoke 主要覆盖页面可见性，不能替代下述 Playwright 生成流程测试。

`build`、`lint` 或相关测试失败时，不得宣称页面完成。

## 2. 组件验收

基础组件：

- Button：默认、悬停、禁用、进行中、危险操作、键盘焦点；
- Input：标签、错误、占位、键盘输入；
- Badge：语义颜色和文本不溢出；
- Drawer / Modal：打开、关闭、Escape、焦点恢复、滚动锁定；
- EmptyState：空数据和下一步动作；
- Thumbnail：缺图、加载、contain / cover、固定比例。

业务组件：

- AssetCard；
- TemplateCard；
- ShotCard；
- ResultCard；
- TaskCard；
- Gallery；
- AssetDetailDrawer；
- GenerationPanel。

业务组件不得自行发明 API 成功、审核通过、正式交付或费用信息。

## 3. Video Studio 主流程

### Happy Path

- [ ] 打开 Video Studio；
- [ ] 选择产品；
- [ ] 选择人物、场景或其他允许素材；
- [ ] 选择模板；
- [ ] 上传区内唯一分镜网格正确显示素材，模板要求可见，按需检查支持缩放与大图；
- [ ] 上传区内支持拖拽及键盘排序、删除，不存在独立分镜序列区；
- [ ] Generate 按钮在输入完整时可用；
- [ ] 创建任务只发生一次；
- [ ] 页面显示 Preparing assets；
- [ ] 页面显示 Generating；
- [ ] 页面显示 Validating；
- [ ] 页面显示 Completed 或 Failed；
- [ ] 结果区显示真实结果或真实错误；
- [ ] 结果详情可从当前工作区打开，不丢失上下文。

### Failure / Recovery

- [ ] 无素材时无法提交；
- [ ] 无模板时显示可执行提示；
- [ ] 网络失败显示可重试状态；
- [ ] Provider 结果未知时不自动重新付费；
- [ ] 重复点击不会创建重复任务；
- [ ] 任务详情刷新后状态来自服务端；
- [ ] 失败任务可进入 Task Center；
- [ ] 下载失败不会被误显示为重新生成；
- [ ] 页面刷新后不丢失可恢复的任务详情链接。

## 4. Image Studio 主流程

- [ ] Product、Character、Scene 选择器可区分类型；
- [ ] 生成图片前展示预计输出信息；
- [ ] 生成中每个阶段可感知；
- [ ] VariationGrid 使用固定媒体比例；
- [ ] 选择结果不会自动写入 QUALIFIED 或 Approval；
- [ ] 审核失败要求理由；
- [ ] 合格结果才可以进入 Create Video；
- [ ] 图片任务完成通知不会因离开页面而丢失；
- [ ] 账户切换不会展示另一账户的本地草稿或任务。

## 5. Task Center

产品展示层六态：

```text
queued
preparing
running
validation
completed
failed
```

- [ ] 六态均有中文可读标签；
- [ ] 后端更细 phase 通过单一映射层展示；
- [ ] 原始 phase 仍可在技术详情查看；
- [ ] FilterTabs 与查询参数保持一致；
- [ ] 列表、详情、返回和滚动恢复可用；
- [ ] Drawer 打开与关闭不丢失筛选条件；
- [ ] 重试动作遵守服务端 actionCapabilities；
- [ ] 未知结果不显示为 completed；
- [ ] 结果审核、最终批准和 Deliverable 有明确区分。

## 6. Library

- [ ] Character、Product、Scene、Template 分类可切换；
- [ ] 资源卡片显示真实名称、缩略图和类型；
- [ ] 空状态提供下一步动作；
- [ ] DetailDrawer 可打开、关闭和恢复焦点；
- [ ] 删除、编辑和选择遵守现有权限；
- [ ] 资产选择后可返回 Studio 并保持上下文；
- [ ] 不生成虚假的版本、来源、费用或审核元数据。

## 7. 视觉与响应式验收

每个完成页面检查：

视口：

```text
1440 × 900
1024 × 768
768 × 1024
390 × 844
```

检查项：

- [ ] 没有页面横向溢出；
- [ ] 视觉中心是画布、素材或结果；
- [ ] 栏宽依据任务优先级而非固定三栏，移动端与 DOM 动线一致；
- [ ] 文字适配容器，不遮挡相邻内容；
- [ ] 卡片、面板、按钮圆角符合 Design System；
- [ ] 状态颜色使用语义 token；
- [ ] 不出现无意义渐变、装饰性光球或后台式统计墙；
- [ ] Loading 文案不是单独的 `Loading...`；
- [ ] 空、错误、进行中、完成四类状态均有设计；
- [ ] 资源图片和视频不被错误裁切；
- [ ] 低宽度下按钮和状态标签仍可操作。
- [ ] Video Studio 不设置永久空源图画布，每个分镜默认只出现一次；
- [ ] 空上传区不渲染分镜占位，七张图在桌面与移动端换行，操作无需横向滚动；
- [ ] 模板名称不重复展示，摘要保留真实状态、画幅和数量约束，完整配方可打开；
- [ ] 桌面素材准备和生成配置并列，提交位于两区之后；移动端保持同一 DOM 动线；
- [ ] 上传区没有遗留 hover 阴影，不把整块素材准备区包装为浮动卡片；
- [ ] 1440×900 配置两张图与历史主体后，付费提交按钮无需滚动可见；
- [ ] 放大检查关闭后返回原分镜焦点，保留拖拽、键盘排序与删除；
- [ ] 1102px 中间宽度提交摘要不挤成竖排，所有宽度付费确认文案可见；
- [ ] 记录任务权重假设和人工测量缺口，不将测试桩流程通过等同于效率验证。

## 8. 可访问性

- [ ] 主要操作可通过键盘完成；
- [ ] 图标按钮有 `aria-label`；
- [ ] Drawer / Modal 有标题和正确关闭行为；
- [ ] 动态状态使用 `role=status` 或等价语义；
- [ ] 错误使用 `role=alert` 或等价语义；
- [ ] 焦点不会进入已关闭的浮层；
- [ ] `prefers-reduced-motion` 下不依赖动画传递信息；
- [ ] 颜色不是传达状态的唯一手段。

## 9. 浏览器流程

使用现有 Playwright 和离线 fixture；API 写入仅允许隔离测试桩，禁止落到正式后端或真实付费 Provider。现有 `scripts/ui-pages-offline-check.mjs` 可作页面回归入口，但其当前覆盖不包含生成/批准操作。

记录报告目录、source HEAD/文件 hash、浏览器版本、视口、截图、断言和测试限制。Playwright 未可用时报告缺口，不能用静态组件渲染测试替代浏览器操作证明。

Video Studio：

```text
open page
→ select asset
→ select template
→ create task
→ observe status
→ open result
```

Image Studio：

```text
open page
→ choose Product / Character / Scene
→ generate fixture
→ select output
→ review
→ transfer qualified output to video
```

Task Center：

```text
open page
→ filter
→ search
→ open detail drawer
→ close and restore list context
```

## 10. 发布前声明门槛

允许声明：

```text
TASK_DONE
FUNCTIONALLY_VERIFIED
INTEGRATION_VERIFIED
```

必须有对应测试和浏览器证据。

不允许仅凭代码存在、Mock PASS 或静态截图声明：

```text
INFRASTRUCTURE_READY
PRODUCTION_LOOP_READY
PRODUCTION_READY
ZERO_TOUCH_ELIGIBLE
```

这些状态还需要后端、真实生产链、审核/交付证据和必要的运行环境证据。

本次仅固化文档：运行 build/lint/unit 基线；不执行浏览器生成流程，不更新页面验收状态，不宣称效率或生产质量改善。
