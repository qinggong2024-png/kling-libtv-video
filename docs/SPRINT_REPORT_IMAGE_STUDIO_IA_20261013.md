# Sprint Report：Image Studio 信息架构重构

日期：2026-10-13
范围：前端页面、导航和组件拆分；不修改后端 API、生成引擎、任务模型或数据库。

## 完成

- 首屏三个主要入口依次为“图生图 / 文生图 / 批量生产”；生图记录放在其后。320×720 手机视口也完整显示三个入口。
- 图生图提供商品图、人物图、受控提示词、比例、数量、生成按钮，模型与分辨率默认折叠。直接复用现有图像编辑流程，仅提交当前套装；不要求用户进入批量套装列表。
- 批量生产先显示“批量创作 / 产品套装 / 分镜生产”。复杂批量编辑器进入第三级；产品套装页只显示素材管理，分镜生产入口选择现有分镜模式。
- 文生图保持一级入口，提示词按账号范围保存到浏览器。现有接口没有纯文本生成能力，页面明确标为暂未开放并禁用生成按钮。
- 生图记录独立承载任务列表、恢复、结果选片和审核入口，重新生成回到批量编辑器。
- 保留持续挂载的运行容器及原有草稿、轮询、通知、审核、恢复和视频交接；导航使用现有 query 结构，与主导航及浏览器前进/后退同步。
- `ImageStudio.tsx` 从 1132 行拆到 548 行；表单、素材上传和审核/比较/选片展示分离，保留旧 ImageCenter 导出兼容。

## 修改

- 页面：`ImageStudioHome`、`ImageToImageStudio`、`TextToImageStudio`、`BatchStudio`、`BatchCreationView`、`ImageRecords`。
- 复用展示：`shared/ImageAssets`、`shared/GenerationConfig`、`ImageResultTools`。
- 运行与导航：`ImageStudio`、`imageStudioNavigation`、`app/useAppNavigation`。
- 样式及隔离检查：`styles.css`、导航单测、Image Studio 浏览器脚本、既有 creative-shell / image-review 检查。

## 测试

- testing：build、lint 通过；57 个 Vitest 文件、405 项测试通过。
- Image Studio 隔离浏览器：1440×900、1024×768、768×1024、390×844、320×720 全部通过。
- 覆盖入口首屏边界、顺序、直接图生图提交、原 multipart/幂等键、单套与多套提交范围、产品素材页、分镜模式、已保存草稿恢复、刷新、前进/后退、主导航重置及模拟 502 提交阻断。
- 既有 shell 隔离检查：四视口及任务深链/记录滚动恢复通过，覆盖导演台切回图片工作室。
- 既有图片审核检查：四视口、选片不写审核、只读比较、显式拒绝及焦点恢复通过。
- 证据：`E:/Codex/image-studio-ia-final-testing`、`E:/Codex/image-studio-shell-final-testing`、`E:/Codex/image-studio-review-final-testing`。
- 使用离线 fixture，未调用真实 Provider、付费生成或生产数据写入。生产分支独立验证及源码同步结果见后续同步记录。

## 发现与限制

- `image_generations.py` 现有 fusion/storyboard 都要求 `model.front` 和 `product.front`。本次前端范围不能实现纯文本生成；文生图入口及草稿可用，生成能力仍未开放。
- 原 IndexedDB 保存有 450ms 防抖；刷新恢复验收等待“草稿已保存”。图生图展示保存状态，未完成保存就刷新仍可能丢失尚未写入的修改。
- 502 仍属于运行环境问题；本次只验证异常时阻断新任务，没有修改 API proxy、Windows 服务或重启服务。
- 浏览器通过不代表真实生成质量、服务连通性、人工方向或上线接受已完成。

## 下一步

- 产品负责人验收创作优先、生产下沉的信息架构。
- 纯文生图如需开放，应另行定义后端能力与生成合同；本次没有扩展该范围。
- 源码推广后仍需单独进行正式版运行验收。正式版入口为 `http://192.168.30.126:5173/`。
