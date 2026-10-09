# 衣影工坊 Design System

版本：V1.0
日期：2026-10-08
状态：视觉与交互约束冻结

## 1. 技术落点

当前前端实际技术栈是 React + TypeScript + Vite + `lucide-react`。本规范中的组件体系应优先落在现有 `frontend/src/shared/components`、`frontend/src/features` 和 `frontend/src/styles.css` 中。

Next.js、Tailwind、shadcn/ui、Radix UI、Framer Motion 是可选参考，不是当前仓库的强制迁移目标。引入新框架前必须证明能降低风险或显著提高生产效率。

## 2. 视觉方向

目标参考：

- Figma：画布和局部编辑上下文；
- Runway：媒体生产流程和结果反馈；
- Linear：信息密度、状态和键盘友好。

禁止：

- Dashboard 风格首页；
- 大量表格和统计卡片；
- 普通后台 CRUD 卡片堆叠；
- 五颜六色的状态装饰；
- 大面积渐变、装饰性光球或无意义背景图；
- 用文字长按钮替代已有的熟悉图标操作。

## 3. Design Tokens

基础颜色：

```css
--background: #F7F8FC;
--surface: #FFFFFF;
--border: #E5E7EB;
--primary: #2563EB;
--ai: #8B5CF6;
--canvas: #111111;
```

当前项目已有更完整的语义变量（例如 `--page`、`--surface-soft`、`--text`、`--line`、`--success`、`--danger`）。新增样式优先使用现有语义变量；需要对齐本规范时，更新 token 映射，不在业务组件中散落硬编码颜色。

圆角：

```yaml
button: 8px
card: 12px
panel: 16px
canvas: 20px
```

间距使用 8px 网格：

```text
4 / 8 / 12 / 16 / 24 / 32 / 48
```

其他约束：

- 字体使用现有 Inter、Noto Sans SC、Microsoft YaHei 回退栈；
- 字距保持 `0`，不得使用负字距；
- 固定格式区域使用稳定的宽高比、grid track 或 min/max 约束；
- 卡片圆角不超过 12px，除非是明确的画布或浮层；
- 页面区块使用完整布局，不把每个区块再套进卡片；
- 颜色必须表达语义，不能只为了装饰增加颜色。

## 4. 组件层级

### 基础 UI

目标目录：`frontend/src/shared/components/ui`。当前仓库已有 `frontend/src/shared/components/ui.tsx`，迁移时保持导出兼容。

至少提供或统一以下基础组件：

- `Button`
- `Input`
- `Card`
- `Badge`
- `Drawer`
- `Modal`
- `EmptyState`
- `Alert`
- `Thumbnail`

按钮要求：

- 图标按钮必须有 `aria-label` 和 tooltip；
- 破坏性操作使用语义危险色；
- 生成、保存、下载等动作使用明确的进行中和禁用状态；
- 熟悉图标存在时，不用圆角矩形文字模拟图标操作。

### 业务组件

共享业务组件：

- `AssetPicker`
- `AssetCard`
- `AssetPreview`
- `AssetDetailDrawer`
- `TemplateCard`
- `RecipePreview`
- `TemplateSelector`
- `GenerationPanel`
- `GenerateButton`
- `ProgressStatus`
- `GenerationResult`
- `ShotCard`
- `ResultCard`
- `TaskCard`

组件必须通过 props 接收真实数据和动作，不在组件内部伪造 API 成功、审核或交付状态。

模板展示模型至少表达：

```ts
type StudioTemplate = {
  id: string
  name: string
  category: string
  assets: string[]
  promptRules: string[]
  camera: string
  motion: string
}
```

这是 UI 目标模型，不是新的服务端 schema。适配器须从已确认的模板 API 映射；缺少字段显示未配置或隐藏相应动作，不伪造模板配方。素材系统支持 Product、Character、Scene、Template，保持真实 ID、归属和权限。

## 5. 页面布局

### Video Studio

```text
VideoStudio
├── PreparationWorkspace
│   ├── AssetPanel
│   │   ├── Upload + Storyboard（上传区内排序 / 删除 / 检查）
│   │   └── SubjectInput（可选一致性主体）
│   └── GenerationConfiguration
│       ├── TemplateSelector（紧凑摘要 / 按需配方）
│       └── CreativePanel（生成方式 / 意图 / 高级折叠）
├── GenerationPanel（两区之后：时长 / 数量 / 付费提交）
├── SourceInspector（按需缩放 / 大图）
└── ResultGallery
```

页面形成“上传并整理素材 → 生成配置 → 提交 → 阶段 → 结果”的纵向工作区，桌面和移动端保持同一 DOM 动线。顶部上传标题、数量和入口组成工具栏，下方仅呈现实际上传的图；可选主体默认一行摘要，展开编辑后可收起而不清空输入。模板和生成方式在下一操作区内并列，低于 800px 转为纵向；统一提交紧随创意配置。当前结构依据见 `VIDEO_STUDIO_BANDS_REVIEW_20261009.md`，替代此前两区并列方案。

每张分镜仅一份缩略表示，网格轨道限制为 104–128px，不随两图或七图数量膨胀；按视口自动换行。空状态不设置序列或大图占位。区域通过留白与分隔线组织，不套浮动面板卡片。Video Studio 局部使用纯色背景和按钮，保留全站其他页视觉。

模板名称不再在选择器下方重复展示，默认仅保留真实状态、画幅及素材数量限制，完整配方使用 Drawer。静态源图预览是支线，不是必经步骤；没有编辑能力时不设置永久大画布。当前依据和可测验收见 `VIDEO_STUDIO_LAYOUT_REVIEW_20261009.md`；20261008 方案已被本轮修订替代，但保留历史证据。

### Image Studio

```text
ImageStudio
├── AssetPanel
├── CreativeCanvas
├── GenerationPanel
├── VariationGrid
└── VideoTransfer
```

### Task Center

```text
TaskCenter
├── FilterTabs
├── TaskQueue
├── TaskDetailDrawer
└── ReviewGallery
```

### Library

```text
Library
├── CategoryNav
├── AssetGrid
└── DetailDrawer
```

## 6. 状态与交互

产品展示层统一使用以下六类状态：

```ts
type TaskStatus =
  | 'queued'
  | 'preparing'
  | 'running'
  | 'validation'
  | 'completed'
  | 'failed'
```

这只是用户理解层，不覆盖后端真实 `phase`、variant attempt、审核和交付状态。映射必须集中在 domain/presentation 层，不能在各页面自行判断。

取消、未知提交、部分成功和待人工确认仍须显示各自的真实标签与动作约束。六态用于正常生成生命周期；无法可靠归类时保留原始状态，不强制将 UNKNOWN / CANCELLED 映射为 failed 或 completed。completed 不授权审核通过或交付。

生成过程必须显示可理解的阶段：

```text
Preparing assets
Generating
Validating
Completed
```

禁止只显示 `Loading...`。

交互约束：

- 编辑详情优先 Drawer / Panel；
- 高级参数使用折叠区；
- 生成按钮在无效输入、进行中和未知结果时正确禁用；
- 未知 Provider 结果不得自动重试或显示为成功；
- 选择结果不等于审核通过；
- 审核结果不等于交付，除非后端返回正式交付状态；
- 重要操作支持 Escape 关闭、焦点恢复和键盘可达；
- 支持 `prefers-reduced-motion`。

## 7. 响应式

必须检查 1440、1024、768、390 四个视口。

- 桌面优先呈现多栏生产工作区；
- 平板收缩侧栏和面板，保留主生产区；
- 移动端将面板转为纵向区块或底部 Sheet；
- 文本不得溢出按钮、卡片或状态标签；
- 固定格式媒体预览不得因内容变化导致布局跳动；
- 不得出现横向页面溢出。
