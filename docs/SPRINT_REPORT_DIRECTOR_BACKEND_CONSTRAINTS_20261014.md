# Director Backend Prompt And Submission Constraints

日期：2026-10-14（Asia/Shanghai）
范围：将关键帧、参考预算和提示词规则移入后台编译与提交边界。

## 完成

- 撤下本轮前序新增的前端预算、拆镜、合帧和复制规划控件；导演页面不再
  自行生成、编辑或持久化本地空间分镜提案。保留现有服务端文档展示。
- 新增后端 `director-visual-plan.v1`：明确区分脚本节拍 Bxx、剪辑镜头 Sxx、
  静态关键帧 Kxx。镜头时长来自脚本，与参考图片数量无关。
- 场景、机位、景别、显式切镜、独立动作段变化拆镜；同镜头内商品面变化、
  新文字细节、遮挡解除补产品锁节点，不因此增加剪辑镜头。
- 兼容判断覆盖场景、机位、景别、人物区域、商品面、手部占用和支撑关系；
  动作起始图进一步要求相同姿态。优先无遮挡、锁项更完整的图片。
- 最小覆盖搜索限制 10000 次；达到限制时如实标 `bounded_cover`。相容的
  多个镜头可复用一张图，正背面等不可相容状态不合并。
- 图片提示词只描述一个姿态和一个手部接触状态；视频提示词描述按节拍
  排列的动作、时窗和显式图片引用，保留人物、衣服、印花和空间约束。
- 关键帧用途显式区分 `STATIC_DISPLAY`、`MOTION_READY_START` 和
  `DISPLAY_KEYFRAME`；默认导演首帧为动作起手式，并记录下一动作、神态、
  视线目标和重心分布。
- 视频输入校验要求动作起始绑定使用 `MOTION_READY_START`，静态展示图不能
  直接成为视频首帧。
- 新包将计划及视频上下文纳入现有冻结文本合同；提交重新计算后台计划，
  不信任页面复制内容或自报的 `ready`、图片数量或引用编号。
- Flow 5 / Kling 7 是用户指定的当前入口总预算，包含商品、人物和场景
  预留。实际提交按真实槽位计数，不按文件 SHA 去重后虚减数量。
- 更严格的 Provider 能力声明继续生效；预检检查实际视频提示词长度，
  不再拿短的图片提示词代替实际 API prompt。
- 旧单图视频投影会丢失首帧、商品引用，本轮对新导演合同拒绝该投影，
  防止提示词引用编号与实际上传内容不一致。

## 修改

- `creative/visual_plan.py`：后台计划、覆盖优化、提示词及引用预算校验。
- `creative/workflow.py`：新包冻结计划和独立视频上下文，分镜继承父包计划。
- `creative/package_contract.py`：人工交接视频稿复用后台时间线；完整 JSON
  在 `provenance.originEvidence.visualPlan` 保留所有关键帧提示词和计划缺口。
- `creative/image_generation_adapter.py`：单图不同时指示动作起点、过程和终点。
- `services/creative_provider_requests.py`：图像/视频编译均检查冻结计划；
  视频 API 参数独立编译，显式绑定现有首帧、分镜和商品参考的真实顺序。
- `services/creative_provider_preflight.py`：检查实际 API prompt 长度。
- `services/controlled_video_adapter.py`：阻断无法保留完整引用的旧单图入口。
- `DirectorStudio.tsx`：移除本地分镜计算、编辑和持久化；
  `DirectorStudio.browser-check.mjs`：验证编辑控件消失。
- 保留既有认证、授权、成本、幂等、物化、来源/审核及 Provider 能力校验。

## 测试

- 本轮作用域同步后的后台回归：testing 与 main 独立各 496 项通过，
  failures / errors / skipped 均为 0；JUnit 耗时分别 449.574 / 454.364 秒。
  两侧作用域 Ruff 通过。这些结果对应当时读取的源码，不覆盖之后的并行修改。
- 前端 testing 58 文件 / 408 项、main 59 文件 / 404 项单测通过；
  两侧 lint / build 通过。构建输出在外部验证目录，没有覆盖正式 dist。
- Director 隔离浏览器流程：两侧均在 1440、1024、768、390 宽度通过，
  每个视口 18 个模拟命令，外部请求为 0；桌面和手机截图已人工查看，
  拆镜、合帧和预算编辑控件消失，未发现内容重叠。
- 全站九页面隔离 smoke：两侧报告均为 9/9 PASS。testing 初次输出
  页面 PASS 但没有报告文件，不作为完整通过证据；2026-10-14 收尾重跑
  确认子进程 exit=0、报告存在、fixture writes=0。main 报告独立存在。
- 浏览器验证使用显式 Chrome 路径，解决原默认 Edge 路径不可用的问题。
  fixture 不读取真实 env、不代理真实 API；临时服务在验证后关闭。
- 外部证据根目录：
  `E:/Codex/validation/director-backend-plan-20261014/`。
  两侧各有 `backend-tests.xml`、`director/report.json`、`ui-smoke.json`；
  构建、缓存及浏览器证据没有同步进生产工作区。
- 本次新增首帧用途、表情、视线及重心指令已压缩到现有图片 Prompt 长度约定内。
- testing 的导演关键帧、Prompt 吸收、Provider 请求、视频适配器、Creative
  Workflow 和 Package Contract 定向回归通过，Ruff 与 `git diff --check` 通过。
- testing 同一批定向回归中仍有一项既有 Provider Options 断言受其他并行改动影响；
  该失败不涉及本次导演帧用途或 Prompt 逻辑。main 同批定向回归全部通过。
- 未执行真实图片、视频或付费请求。

## 发现问题与限制

- 现有 Director 执行合同仅支持 FIRST_FRAME / SHOT_01；本轮没有扩展批量
  生图或多镜头授权。计划需要多镜头、多个关键帧或额外商品面引用时，
  返回明确阻断，不能宣称这类计划已可直接生成。
- 当前导演分析输出还是有限的场景/动作方向，并没有任意自然语言脚本的
  可靠逐节拍解析。新增编译器消费后端结构化 `script_beats`；旧方向出现
  转身、侧背面、特写或切镜等风险词但缺结构化状态时，要求补齐脚本，
  不猜测新展示面、时点或图片内容。
- `STATIC_DISPLAY` 目前作为后端合同用途保留；要进入视频链路，必须改为
  `MOTION_READY_START` 并重新冻结计划，不能由前端或复制文本临时改写。
- 当前后台没有 Flow 实际提交适配器；Flow 5 张规则已进入后端规划/校验，
  但不能把离线预算测试当成 Flow 工具已接收图片的证据。
- 现有图像 Provider 请求仅绑定一张 Canonical front。即使计划声明存在
  背面或人物/场景参考，当前单图边界仍要求实际绑定能力，否则阻断。
- 旧冻结文本仍可读取；没有新计划的历史包提交返回 `VISUAL_PLAN_REQUIRED`，
  需重新确认并冻结包，不直接改写旧 prompt 或旧合同。
- 编译只验证声明状态和合同完整性，不能代替图像像素、英文文字准确性、
  人物真实性或视频中的动态保真审核；计划不等于已生成/审核图片。
- 保留传统固定模板根据用户上传分镜执行的旧规则；导演合同不通过该模板
  重新生成提示词，也不将其图片数量作为导演剧本的镜头数量。
- 没有修改 `.env`、数据库、迁移、付费开关；没有真实生成、部署、正式服务
  重启或 commit。此前 5193 的任务专用预览已停止，正式入口没有重启。

## 同步

- testing 工作区：`E:/Projects/libtv自动化生成`，分支 `codex/testing`，
  本轮 HEAD 为 `23311456de8abaf8a95a615c8b249d8a7831ccb5`。
- main 工作区：`C:/Users/Reel/Documents/libtv-auto-main-sync`，分支 `main`。
  入场 HEAD 为 `986d57a`；收尾 HEAD 为
  `9f22619a639bd278258f814de42269ebee592f9f`，由并行正式服务恢复任务推进，
  本轮没有创建 commit。
- 本轮源码先在 testing 实施，再按文件/定义作用域同步 main；同步时
  13 个任务文件 SHA-256 一致，workflow 的四个相关定义 AST 一致。
  CHANGELOG 与历史报告仅同步本轮条目，保留其他已有内容。
- 收尾比对时，上述 13 个文件中 11 个仍完全一致；testing 的
  `visual_plan.py`、`test_director_visual_plan.py` 已出现并行首帧用途扩展。
  workflow 的 `PackageRevision`、`compile_storyboard_package` 仍一致；
  `PlanRevision` 有并行 frame_purpose 扩展，`compile_package` 有旧脚本
  图片提示词拼接差异。testing 另有与本轮无关的 retry_analysis 行。
- 这些收尾差异没有整文件覆盖或自动提升；因此本轮曾完成作用域同步，
  但当前共享工作区不能宣称两侧源码全部一致或最终回归全部通过。
- 两侧本轮 `git diff --check` 通过；三份前序前端规划专用文件均已撤下。
  两个工作区仍有其他未提交/未跟踪修改，全部保留，未清理或回滚。
- 正式入口仍为 `http://192.168.30.126:5173/`。源码同步不等于线上部署
  或正式运行验收；没有重启正式服务、迁移或改写真实数据库。

## 下一步

- 先收敛并行首帧扩展与紧凑图片提示词的兼容问题，核对 testing / main
  的剩余定义差异；在这些问题解决前不宣布当前版本完成最终验收。
- 如需真正执行多关键帧脚本，必须将已验证的结构化导演脚本和多个已审核、
  已物化的 Kxx 绑定接入受授权的生成合同；不能绕过本轮服务器阻断。
- 在此之前，不以页面可见、提示词可复制或单元测试通过宣称多镜头真实
  生产闭环。真实单产品样本测试和付费生成仍单独授权。
