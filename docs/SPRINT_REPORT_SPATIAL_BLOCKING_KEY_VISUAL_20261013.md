# Sprint Report: Spatial Blocking + Key Visual Selector

日期：2026-10-13  
分支：`codex/testing`  
来源：`AI-Fashion-Creative-Director-v1.13.7.zip` 中的空间关系、Spatial Blocking and Camera Axis、Key Visual Shot Selector 参考文档

## 完成

- 在 Director Studio 规划层增加 `DirectorSpatialPlan`，保存 `scene_id/layout_revision`、空间锚点、世界光源方向和定性布局。
- 增加 `C1/C2/C3` 机位位点、180° 轴线侧、转场类型、机位可达与越轴状态。
- 增加每个镜头的人物起止位置、支撑点、手部占用、世界空间路径、接触状态转移和下一镜连接类型。
- 增加 Key Visual Shot Selector：先建立 `S01..S04` 时间线，再按场景、机位、产品可见性和人物空间状态选择 `K01..K04`。
- 独立记录 `shot_count`、`key_visual_count`、`planned_image_count`、`authorized_image_count`、`generated_image_count`，计划层保持 `planned_not_rendered`。
- 规划快照复用现有 `directorPlanning` 持久化边界，不新增产品工作区或 Provider API。

## 变更

- 新增 `frontend/src/features/director-studio/spatialPlanning.ts` 与对应单元测试。
- 新增 `SpatialPlanningView.tsx`，放置在现有 Production Package 内。
- 扩展 `DirectorPlanningSnapshot` 和恢复读取逻辑，保存空间规划。
- 增加紧凑工作台样式，支持桌面、平板和移动布局。
- 扩展 `DirectorStudio.browser-check.mjs`，覆盖四个目标视口中的面板、计数、合并动作和无横向溢出。

## 测试

- `npm run build`：通过。
- `npm run lint`：通过。
- `npm run test`：`56` 个测试文件、`395` 项通过。
- 相关空间规划、选择器和快照测试：`3` 个文件、`7` 项通过。
- 浏览器 fixture：已加入空间规划断言；实际运行记录待 Playwright 依赖路径确认。

## 发现与限制

- 当前空间数据是 `proposed / planned_not_verified`，没有伪造实测米数、真实像素或 Provider 已接收参考图证据。
- 关键视觉选择只改变规划和计数，不创建图片授权，不触发真实生成，不把文字规划升级为 `IMAGE_READY`。
- 当前离线工作流仍是 `OFFLINE_FAKE_ONLY`，候选不可交付。

## 下一步

- 由人工确认空间规划面板的信息密度与字段优先级。
- 在后端 Creative Package 合同被批准后，再决定哪些空间字段需要服务端版本化与逐镜来源映射。
