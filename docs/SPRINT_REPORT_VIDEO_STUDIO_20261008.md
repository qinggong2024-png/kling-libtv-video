# Sprint Report：Video Studio + Design System

日期：2026-10-08
范围：Sprint 0 + Sprint 1，等待 Checkpoint 1 人工方向验收

## 完成

- Video Studio 形成源素材、主画布、模板与创意配置、分镜、提交、队列与结果的连续工作区。
- 支持本地产品/分镜上传、历史人物主体选择、模板切换、配方抽屉、分镜排序、缩放和大图。
- 任务详情在抽屉中打开；预览视频使用可嵌套原生 Modal，Escape 和焦点恢复已做浏览器验证。
- 生成结果包含待最终审核的真实可播放素材，不把结果出现等同于批准交付。
- 沿用 React/TypeScript/Vite、真实 API 客户端、认证、幂等键、付费确认、审核和交付合同。
- 未开发下一轮 Image Studio、Task Center 或 Library 新页面。

## 修改

- 新增共享 Button、IconButton、Modal、AssetCard、TemplateCard、TemplateSelector、RecipePreview、CreativeCanvas、ShotCard、Storyboard 和 TaskCard。
- 复用已有 Drawer、状态徽标、主体选择器、ResultCard、API 和媒体加载接口，不创建闲置组件。
- 新增集中六态展示映射；UNKNOWN 覆盖正常状态，取消、待审和部分完成保留原语义。
- Studio 样式限定在工作区内；移除该工作区旧大卡片和固定提交栏，保持 Canvas 优先。
- 增加同步提交锁、未知提交锁定、批量组数量/时长校验和退出批量操作。
- 批量成功组从剩余提交集合中移除，局部失败后再次提交不会重复创建成功组。
- 保留图片转视频来源 ID；结果时长读取持久化设置，不显示固定虚构时长。
- 模板/风格读取失败支持重新读取；视频获取或解码失败显示错误。
- 新增无代理、无 .env、无数据库的离线 API fixture、Playwright 流程和安全预览入口。

## 测试

- testing：build、lint 通过；Vitest 33 文件、234 项通过。
- testing：Video Studio Playwright 10 个用例通过；实际视口 1440x900、1024x768、768x1024、390x844。
- 10 个用例包含四种尺寸正常流程，以及未知提交、缺模板、模板读取失败恢复、无效批量、批量部分失败和明确拒绝。
- 正常流程验证真实控件、请求模板/人物 ID、付费确认字段、一次提交、五阶段刷新、深链接刷新、画布尺寸和无横向溢出。
- 视频为浏览器本地录制的合成 WebM；检查 videoWidth/videoHeight/currentTime，证明解码与播放，不证明真实 Provider 输出质量。
- 抽屉内播放验证两个原生 dialog 的层级、Escape 仅关闭最上层以及焦点恢复。
- 既有隔离页面回归 66 用例通过；图片审核选择/比较/四视口检查通过；fixture 与 smoke 脚本 14 项测试通过。
- 截图检查涵盖已配置工作区、窄屏、结果和嵌套播放。单元组件测试为静态渲染合同，不单独作为交互验收。
- 证据根目录：`E:/Codex/visualizations/2026/10/08/01a11aa7-388c-7c00-857f-b320ea54a013`。
- 子目录：`video-studio-testing`、`pages-testing`、`review-testing`；报告记录源码 HEAD/hash 和 Edge 版本。
- main：build、lint 通过；Vitest 34 文件、230 项通过。build 输出到外部 `main-build`，未覆盖正式目录 dist。
- main：Video Studio 10 用例、既有页面 66 用例、图片审核检查、fixture/smoke 14 项测试分别通过；Studio 外部请求为 0。
- main 证据子目录：`video-studio-main`、`pages-main`、`review-main`；浏览器 Edge 154.0.4258.62。
- 源码推广：testing `70b90cd` → 实际 main `e3ae81d`；仅本轮 21 个源文件、测试、脚本和文档。
- 比较推广前后范围以及两个分支修改文件，保留 main 主体接口/错误处理、任务真实错误信息与 Required Hard Gates 审核文案，不覆盖生产树。
- 没有同步真实 .env、密钥、运行状态、缓存、生成媒体、构建产物或用户 ZIP。

## 发现问题

- 修复测试 mock 的不完整 Task 类型和模板控件定位歧义。
- 修复旧 CSS 覆盖 Studio 容器、抽屉阶段被隐藏、390px 状态徽标隐藏、结果封面裁切和主体详情上传区过高。
- 修复同一渲染周期重复点击、UNKNOWN 仍可提交、批量错误组被静默过滤及部分成功后重复提交成功组的风险。
- 已有未知提交 intent 虽写入本地存储，本轮不实现跨刷新恢复向导；刷新后的恢复和计费确认仍须走既有任务/运营核对流程，不能推导为可安全再次付费。
- 冻结路由保留既有 query-view/任务深链接兼容方式；本轮不进行四工作区 URL 路由迁移。
- 没有真实付费调用、真实生成质量验收、生产写入、数据库迁移、服务重启或远程推送。
- 未实测新员工上手时间、点击减少量、生产耗时、全量对比度、200% 缩放和性能门槛。
- 不声明 PRODUCTION_READY、PRODUCTION_LOOP_READY 或 ZERO_TOUCH_ELIGIBLE。

## 下一步

- 本轮源代码已同步至实际 main，相关文档随验证记录同步；不是线上发布完成声明。
- 安全本地预览：`http://127.0.0.1:5187/studio/video`，只模拟生成，最后停在待人工审核，不伪造批准交付。
- 正式版入口仍是 `http://192.168.30.126:5173/`；本轮未对该入口执行真实生产验收或服务重启。
- Checkpoint 1：产品负责人确认 Video Studio 的视觉方向与操作路径。
- 确认方向后才启动 Image Studio；真实 Provider 与发布验收另行授权。
