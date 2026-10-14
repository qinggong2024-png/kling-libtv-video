# Sprint Report：三页图片上传框统一

日期：2026-10-14
范围：导演台、图片工作室、视频工作室的图片上传入口。

## 完成

- 三页复用 ImageUploadTrigger，共用图标、两行文字、边框、颜色及交互状态。
- 标准宽度 320px、最大宽度 100%、最小高度 72px、圆角 8px；移动端保持左对齐。
- 导演台保留商品预览与更换入口，图片工作室保留参考图和批量素材处理，视频工作室保留分镜上传与独立批量导入入口。

## 修改

- 新增 shared/components/studio/ImageUploadTrigger.tsx 与 imageUploadTrigger.css。
- 接入 DirectorStudio、ReferenceImageUpload、ImageAssets、ProductionComposer。
- 新增 scripts/ui-upload-consistency-check.mjs，检查样式一致性、键盘文件选择、本地预览及无写入行为。
- 局部源码同步至实际生产 main，保留其他并行修改；未同步秘密、运行状态或生成产物。

## 测试

- codex/testing：build、lint 通过，63 文件 / 429 项单元测试通过。
- main：build、lint 通过，64 文件 / 425 项单元测试通过，构建输出到外部验证目录。
- 两侧上传一致性检查各 12 场景通过，覆盖 1440、1024、768、390px。
- 两侧视频流程各 13 场景通过，图片工作室各 5 视口通过，导演台移动检查各 66 项通过。
- testing/main 隔离页面 smoke 各 9 入口通过。
- 两侧共享组件、导演和图片接入文件、专项脚本及本报告哈希一致；ProductionComposer 的本轮上传导入与 JSX 一致，保留 testing 并行新增的提交校验与恢复动作差异，不覆盖生产文件整树。
- 两侧本轮文件 git diff --check 通过。
- 正式页面三页只读检查并保存截图，返回原视频工作室入口；维护模式保持启用。
- 证据根目录：E:/Codex/visualizations/2026/10/14/01a139bb-0920-79e1-aa74-9ce68b884230/。
- 主要报告：upload-testing-final/result.json、upload-main/result.json、upload-video-main-final/result.json、upload-smoke-final.json、upload-smoke-main.json。

## 发现问题

- 旧导演台和移动端选择器会覆盖共享上传框尺寸及对齐，已增加局部优先级规则并通过四视口一致性检查。
- 并行浏览器检查初次出现导航超时；降低并发后重跑视频和 smoke 均通过，未把超时计为通过。
- 并行历史模块同步曾短暂造成正式页缺少导入文件；文件补齐后正式页恢复，本轮未修改历史业务。
- 本次验证使用隔离 fixture 和合成素材，没有真实上传 API 写入、付费生成、迁移或服务重启。

## 下一步

- 用户验收三页统一后的上传入口；产品方向与上线审批仍由用户决定。
- 源码同步不等于部署或付费生成授权。
