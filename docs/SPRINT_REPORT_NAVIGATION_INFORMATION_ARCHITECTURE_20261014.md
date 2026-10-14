# Sprint Report：导航与信息架构

日期：2026-10-14
范围：产品主导航、生成资产、设置内品牌资产库和任务详情返回

## 完成

- 外部主导航顺序为：导演台、图片工作室、视频工作室、任务中心、生成资产。
- 移动端底部保留五个产品入口，设置通过顶部图标进入。
- 生成资产从既有任务及图片批次历史读取逐结果审核通过的媒体，支持搜索、
  媒体类型筛选、图片预览和既有视频结果操作；部分失败和重试不会隐藏已经批准的结果。
- 原内容与主体维护能力移入设置，作为低频维护的品牌资产库；既有 API、编辑、
  权限和键盘筛选行为保留。
- 任务中心保留 Prompt、过程、审核、版本和重新提交链路；生成资产中的视频任务
  详情可返回原 query-view 入口并恢复点击时保存的滚动位置。

## 修改

- 应用分发和导航：App、AppShell、useAppNavigation。
- 结果与维护：GeneratedAssetsView 及测试、ContentLibraryView 及测试、
  SettingsView、局部 styles.css。
- main 只补入 getAllTaskHistory 和图片结果所需 optional synthetic/outfitName
  类型，不覆盖其 API/type 文件内的生产专属内容。
- 验收：ui-smoke、ui-pages-offline-check、ui-creative-shell-check、
  ui-director-delivery-check 和 ui-page-responses。
- 文档：CHANGELOG 和本报告。

## 测试

| 工作区 | Build | Lint | Vitest | 隔离浏览器 |
| --- | --- | --- | --- | --- |
| codex/testing | 通过 | 通过 | 61 文件 / 422 项通过 | 完整页面 64 项通过；最终生成资产专项 8 项通过 |
| 实际 main | 通过 | 通过 | 62 文件 / 418 项通过 | 完整页面 64 项通过；最终生成资产专项 8 项通过 |

- 四种视口：1440、1024、768、390。完整矩阵覆盖视频页、任务中心、生成资产、
  设置及管理页的适用 populated/empty/error/loading 状态和管理权限边界。
- 最终专项覆盖已审核视频及图片、排除未审核/合成图片、搜索、媒体筛选、
  图片预览与 Escape 关闭、任务深链接返回和滚动恢复。
- 两侧完整矩阵和最终专项均没有外部请求、写请求或未匹配 API 请求。
- Build 最终输出至仓库外证据目录，未覆盖正式 dist。
- 正式入口 http://192.168.30.126:5173/ 在线 smoke 未通过：部分路由页面就绪
  检查失败，library/settings 和管理入口出现登录边界或缺少 UI_SMOKE_USERNAME /
  UI_SMOKE_PASSWORD。没有凭据时未尝试登录；不宣称正式在线验收通过。
- 以下路径均在 E:/Codex/visualizations/2026/10/14/ 下：
  testing 完整证据 libtv-navigation-ia-acceptance-final5/result.json；
  main 完整证据 libtv-navigation-main-acceptance/result.json；
  最终专项 libtv-navigation-testing-assets-verified/result.json 和
  libtv-navigation-main-assets-verified/result.json；
  在线 smoke libtv-navigation-formal-smoke.json。

## 发现问题

- 旧脚本断言“视频制作”和独立内容库 API 状态，已按当前工作室标题和新信息架构
  更新。生成资产的历史加载/失败状态没有作为独立页面状态验收；不把这一缺口
  隐藏为完整错误恢复验收。
- fixture 增加图片历史、导演历史和 AI quota 的合成只读响应，完成记录含显式
  人工批准信息；fixture 不代表真实数据或 Provider 结果。
- 并行工作持续修改测试目录的导演档案、图片档案、AI 额度、后端和局部样式；
  本轮没有回退这些改动，也没有整树推广。
- 测试通过不代表 Checkpoint 1 方向或 Checkpoint 2 上线已获人工接受。

## 同步与下一步

- 导航、生成资产、品牌资产库、返回路径、相关测试/脚本及本报告已局部同步到
  C:/Users/Reel/Documents/libtv-auto-main-sync 的 main 工作目录。
- 保留 main 的现有图片历史实现及生产专属差异；不推广并行导演/图片档案模块、
  AI 计费逻辑、后端、secrets、真实 .env、运行状态、缓存或生成物。
- 本轮改动保持工作目录状态，没有提交、推送、部署、重启、迁移、真实付费生成
  或生产业务数据写入。
- 产品负责人确认信息架构；具备共享认证凭据后再完成正式入口在线验收。
