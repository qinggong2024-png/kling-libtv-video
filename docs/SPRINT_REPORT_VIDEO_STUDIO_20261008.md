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
- 生产同步与 main 的独立验证结果在同步后补记。

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

- 同步本轮源代码、测试和文档到实际 main 目录，保留生产专属差异、配置和运行状态。
- 提供只模拟生成的本地预览，不把它称为正式版。
- Checkpoint 1：产品负责人确认 Video Studio 的视觉方向与操作路径。
- 确认方向后才启动 Image Studio；真实 Provider 与发布验收另行授权。
