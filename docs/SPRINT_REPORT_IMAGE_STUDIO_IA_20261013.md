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
- 使用离线 fixture，未调用真实 Provider、付费生成或生产数据写入。

## 发现与限制

- `image_generations.py` 现有 fusion/storyboard 都要求 `model.front` 和 `product.front`。本次前端范围不能实现纯文本生成；文生图入口及草稿可用，生成能力仍未开放。
- 原 IndexedDB 保存有 450ms 防抖；刷新恢复验收等待“草稿已保存”。图生图展示保存状态，未完成保存就刷新仍可能丢失尚未写入的修改。
- 502 仍属于运行环境问题；本次只验证异常时阻断新任务，没有修改 API proxy、Windows 服务或重启服务。
- 浏览器通过不代表真实生成质量、服务连通性、人工方向或上线接受已完成。
- main 的全站 shell 脚本四视口页面检查通过，但任务详情返回后的精确滚动位置断言超时。隔离对照撤去新增导航事件仍复现；初次取样位置 2601 超出返回页最大滚动范围 1766，等待网络空闲后仍观察到 6–47px 偏移。未修改 Task Center / Drawer / 任务时序业务，未把这项检查记为通过，保留为独立待查项。

## 源码同步与生产分支验证

- 测试源码提交：`e358a49`、`469973d`；生产源码提交：`912fe25`、`de411ee`。
- 使用实际 production checkout `C:/Users/Reel/Documents/libtv-auto-main-sync` 的 `main`，从测试仓库取回指定提交后逐笔 cherry-pick；没有通过测试仓库的陈旧 main 引用覆盖生产目录。
- 本次推广的 19 个文件 Git blob 与测试提交逐一一致，保留其他会话的导演台代码与文档变化、生产专有文件及双方未跟踪运行报告和用户 ZIP。
- main 独立 build、lint 通过；58 个 Vitest 文件、401 项测试通过。测试与生产分支原有差异保留，因此总测试数量不同。
- main 五视口 Image Studio 完整隔离流程全部通过；图片审核四视口回归通过。main 全站 shell 的滚动恢复结果按上文如实记录。
- main 构建输出位于 `E:/Codex/image-studio-main-build`，未覆盖生产运行产物。证据目录：`E:/Codex/image-studio-ia-final-main`、`E:/Codex/image-studio-review-final-main`、`E:/Codex/image-studio-shell-final-main`。
- 本地离线界面预览位于 `http://127.0.0.1:5188/?view=images&pane=image`；仅本地预览，所有写请求阻断，生成按钮已验证禁用。
- 源码同步成功；未部署、重启服务、执行迁移、写入生产数据或调用付费 Provider。双方最终工作树只保留其他会话/用户改动与既有未跟踪文件。

## 下一步

- 产品负责人验收创作优先、生产下沉的信息架构。
- 纯文生图如需开放，应另行定义后端能力与生成合同；本次没有扩展该范围。
- 源码推广后仍需单独进行正式版运行验收。正式版入口为 `http://192.168.30.126:5173/`。
