# Director Keyframe Execution

日期：2026-10-14（Asia/Shanghai）
范围：后台结构化拆镜、多关键帧冻结、审核、引用编译及提交前约束。
本报告接续 `SPRINT_REPORT_DIRECTOR_BACKEND_CONSTRAINTS_20261014.md`；
前序报告的测试结果仅代表其当时源码，本轮结果独立记录。

## 完成

- 区分脚本节拍 Bxx、剪辑镜头 Sxx、关键帧 Kxx 和执行槽位。
  K01 使用 FIRST_FRAME；K02、K03 分别使用 SHOT_01、SHOT_02。
  SHOT_nn 是兼容旧合同的存储/授权标识，不代表第 nn 个剪辑镜头。
- 场景、机位、景别、显式切镜和动作段变化记录拆镜原因。
  同一连续镜头的正背面或侧正面转换保留商品锁关键帧，不额外切镜。
- 相容状态复用印花清晰、锁项更完整的代表图。细微神态、视线和重心变化
  不单独增加图片，但视频时间线保留各节拍自己的神态和下一动作。
- 关键时刻使用节拍内的显式秒数；缺失时点的多状态脚本在视频编译时阻断。
  结构化视频时长必须与脚本一致，不能为适配模型默默缩短。
- 每个补充关键帧具有独立图片提示词、冻结合同、授权、审核和选择。
  授权一次仅覆盖一个执行槽位，保留既有成本、幂等、UNKNOWN 和停止规则。
- 补充分镜生图绑定原始商品图及已审核首帧，保持人物和穿搭；后续场景
  使用自身的摄影关系，不再继承首帧场景/动作指令。
- 原始侧背面依据来自冻结 ProductVersion 中的 product_view_uploads。
  上传必须属于当前用户、登记于商品来源列表、不是生成输出，并通过字节哈希校验。
  图片与视频提示词明确区分原始 front/side/back 商品参考的编号和用途。
- 视频绑定全部已审核 Kxx，按首次使用时序排列，商品参考排在其后。
  单关键帧脚本无需为了旧 SHOT_01 合同额外生成同内容图片。
- Flow 5 / Kling 7 是用户指定的入口总预算，包含所有实际参考槽位。
  更严格的已验证能力继续收窄预算；超额、缺图、错绑、失效审核和旧合同阻断。
- 增加纯本地视频参数绑定函数，可将预检物化输入交给既有 Kling payload
  构建器离线核对；函数不提交、不授权，也不创建视频任务。

## 修改

- creative/visual_plan.py：时点校验、拆镜/关键帧原因、执行槽位映射和节拍提示词。
- creative/workflow.py：结构化脚本输入、多关键帧包、场景独立摄影关系与引用角色。
- services/creative_workflow.py：原始商品面解析及逐槽位授权/生成/审核/选择。
- services/creative_video_bridge.py：多来源审核、血缘、授权链与完整输入指纹。
- services/creative_provider_requests.py：逐槽位图片请求、多图视频请求、
  商品面引用、时长和 multi_shot 一致性。
- services/creative_provider_preflight.py：可变引用组、显式多镜头能力声明，
  根据实际 PNG/JPEG/WEBP 格式命名临时输入，不改原始对象或图片字节。
- services/creative_provider_submission.py、creative_provider_input_lease.py、
  creative_provider_executor.py：扩展执行槽位类型并保留既有提交边界。
- services/creative_video_provider_adapter.py：本地参数绑定及顺序/文件哈希验证。
- 三份相关测试与 openapi.yaml 的 script_beats 字段说明。
- 本轮未修改前端页面、真实配置、环境变量、数据库结构或运行服务。

## 测试

- 首轮新增关键帧用例：10 passed / 1 failed，失败是测试引用不存在的
  dev_auditor_user_id；已改为隔离测试中随机的其他用户 UUID。
- 修正并独立检查跨场景 Prompt 后：新增关键帧与 Prompt 吸收测试共 55 项通过。
- testing 完整相关回归：529 passed / 0 failed，556.64 秒。
  该轮随后仅移除未使用的局部变量，并补一项 SHOT_02 图片执行器测试。
- testing 最终关键帧与 Prompt 吸收复验：56 passed / 0 failed，15.50 秒；
  包含上述新增槽位票据、错槽拒绝和假适配器输入顺序检查。
  首次追加测试错误地读取 result.ticket，已按现有结果合同验证 ticket_id 并复验通过。
- main 独立完整相关回归：530 passed / 0 failed，267.82 秒。
  与 testing 的 529 项广泛回归加最终 56 项聚焦复验分别记录，不虚报为两侧同一轮结果。
- 两侧本轮作用域 Ruff 和 git diff --check 均通过。
- 外部证据：E:/Codex/v/kf20261014/，分别为 t-final/junit.xml、
  t-keys2/junit.xml 和 m-final/junit.xml。
  守护 runner 的全源哈希不包括 test_director_*；推广另外逐文件核对这三份测试。
  13 个本轮源码/测试的完整双侧 SHA-256 另存 final-source-manifest.json。
- 验证使用 scripts/run_creative_targeted_tests.py，在外部短路径证据目录创建
  独立 SQLite 和对象存储。子进程不读取真实 .env，禁止外部网络连接/监听。
- Kling 只调用本地 build_request_payload；测试另设 Provider submit/upload 禁止桩。
  没有真实生图、生视频、付费请求或生产数据写入。
- 没有新增界面交互，本轮不把历史浏览器验收作为新的页面验收。

## 发现问题与限制

- 结构化输入有确定性校验；现有 Director 尚未提供任意自由文本广告脚本的
  完整自动逐节拍解析。本轮没有增加 LLM 调用或把关键词匹配当作语义理解。
- 覆盖优化依赖结构化场景/机位/姿态等值。搜索最多 10000 次，达到限制标记
  bounded_cover，不能承诺所有复杂脚本都得到全局最少图片。
- 桥接仍要求 OFFLINE_SYNTHETIC_ONLY 来源，隔离测试关键帧是占位素材。
  本地 payload 能正确引用图片，不证明图片表现了计划场景或印花文字正确。
- 原始商品面登记与哈希是来源证明，不是 OCR、空间关系或真实人物像素审核。
- Flow 仅有预算规划，尚无本轮实现的 Flow 实际提交适配器。
- 本轮没有增加 live 视频执行器、真实关键帧资格回写或自动批量付费生成。
  既有 Live Director 命令限制保持，不能宣布网页多关键帧真实生成已全程打通。
- 人物/场景额外参考仍需真实绑定能力，当前没有凭空创建引用来消除阻断。
- 旧冻结包仍可读取；旧计划不能自动获得新时点/槽位语义，重新执行需显式
  确认并冻结有效新包。超过实际 Prompt 长度限制的脚本也会被阻断。
- 视频聚合请求保留旧 shot_id=SHOT_01 兼容标识；真实来源以 references 中
  的 Kxx、独立 package/candidate/output 血缘为准，不把聚合标识当作只有一镜。

## 同步

- testing：E:/Projects/libtv自动化生成，codex/testing，
  HEAD 23311456de8abaf8a95a615c8b249d8a7831ccb5。
- main：C:/Users/Reel/Documents/libtv-auto-main-sync，main，
  入场 HEAD 9f22619a639bd278258f814de42269ebee592f9f。
- 13 个源码/测试文件已推广，逐文件 SHA-256 一致；openapi.yaml 只增加
  Command.script_beats，CHANGELOG 只增加本轮条目，没有覆盖其他任务的内容。
- 相关 Reality、Text Contract 和 Prompt 吸收测试的分支差异为行尾格式，
  不做无关整文件同步。main 独立验证通过，13 个源码/测试收尾哈希一致，
  本报告同文同步到 main；本轮作用域同步成功。
- 两工作区有其他任务的未提交/未跟踪修改，全部保留；没有提交 commit、
  清理文件、同步 secrets/运行数据或重启服务。
- 正式入口仍为 http://192.168.30.126:5173/；源码同步不代表线上部署或运行验收。

## 下一步

- 将现有 Director 的真实脚本输出接入经过验证的结构化节拍合同，覆盖
  侧正面、正背面、文字特写、连续动作和换场景的实际广告案例。
- 接通真实已审核关键帧来源与视频执行器之前，先验证真实图片资格、血缘、
  逐槽位授权和提交参数一致性；沿用既有安全/计费合同。
- 经单独授权后再做单产品实测，分别记录代码/合同、Prompt 和模型表现问题。
