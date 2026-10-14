# Sprint Report：Director Plugin V1.13.15 增量吸收

日期：2026-10-14
范围：摄影因果编译、最终 Prompt 有界语义预检、购买理由与视频脚本适配。

## 完成

- 从用户提供的 `F:/Users/Reel/Downloads/plugin (3).zip` 核对两份版本配置及
  V1.13.14 Compact Reality Compiler、V1.13.15 Meta Creative Rules。
- ZIP SHA-256：
  `ca4ae032976b001ef3ac45ab029a218092f594614e5006701e625955e5fee2fc`。
- 附件作为规则参考；不执行插件安装、发布、生成或其宿主工作流指令。
- 沿用 Reality 六维、已有包版本和 Registry、Text Contract、人工交接及授权。
  没有新增 Agent、DNA 维度、评分平台、工作区、API 表单或数据库迁移。

## 修改

- `creative/reality_evidence.py`
  - 新包在现有六维记录内保存 compiler version、拍摄模式和因果句。
  - 最多两组 trigger → physical relation → visible result 进入最终 Prompt。
  - 支持自然轻摆拍、身份照、镜自拍、前摄自拍、无人商品；抓拍要求明确的
    拍摄者、拍摄动机、注意力和身体状态，缺失不会自动编造朋友、道具或事件。
  - 泛化 UGC、自然光、毛孔或噪点不能代替具体关系；内部六维知识仍保留。
- `creative/workflow.py`
  - 新图片包采用紧凑摄影关系，保留原始商品设计、字样、颜色、版型、状态、
    指定景别以及显式用户锁。
  - 用户指定的拍摄状态、相机和景别优先于方向中的未锁定默认值；
    避免指定全身景仍并存默认中景，继承旧状态与新锁冲突时预检拒绝。
  - 分镜继承父包的确切 Prompt 和摄影关系；修订使用已冻结关系，不重建默认值。
- `creative/text_contract.py` / `services/creative_workflow.py`
  - 在已有冻结环节与执行前 Text Contract 中检查 capture intent、因果句保留、
    SKU/广告可见性和已知矛盾。
  - 未满足时在冻结前返回 `PROMPT_PRESERVATION_REPAIR_REQUIRED`；
    E1 不重写已冻结 Prompt，也不自动调用模型或重新生成。
  - 无 compiler 标记的历史包沿用原校验；哈希、授权、UNKNOWN 与恢复合同保留。
- `creative/brand_dna.py` / `creative/package_contract.py`
  - 从冻结 Product truth fields、用户目标和品牌受众形成一个购买理由判断。
  - 缺商品特征时保留 unresolved；没有匹配的购买证据时只标 hypothesis。
  - 用户确认的购买记录须匹配 Product ID、商品来源 SHA、受众、有效时间窗、
    正购买数、购买指标和归因来源，才标 observed_with_scope。
  - 当商品特征没有被表达时，只补一个已有展示瞬间的职责；不新增剧情、
    道具、对白、触摸动作、镜头或时长。
  - 显式冻结视频稿原样保留；有范围证据且脚本匹配的普通 OOTD 母体保留。
  - 原始图片 Prompt、包 hash、既有九项内容合同不变；判断明细进入已有
    provenance/originEvidence，摄影约束进入已有 qualityChecklist。

## 测试

- testing：13 个定向测试文件、261 项通过，其中本轮新增 44 项。
- main 独立复验：相同 13 个文件、261 项通过。
- 两侧 Ruff 与本轮 `git diff --check` 通过。
- testing JUnit：`F:/Temp/creative-targeted-7d9kiqyn/junit.xml`。
- main JUnit：`F:/Temp/creative-targeted-o3sw9ulv/junit.xml`。
- 使用现有 `run_creative_targeted_tests.py`，隔离临时 SQLite/对象目录，
  禁止网络连接、Provider 和付费生成；未使用真实 `.env` 或生产数据库。
- 覆盖紧凑编译、五类拍摄状态、抓拍缺信息、泛化描述、仅展示参考图、商品
  与用户锁、冲突指令、冻结前拒绝、已冻结文本 gate、父包继承与历史兼容。
- 覆盖 SKU 特征/购买假设、用户目标优先、单点修订及幂等、普通 OOTD、
  已确认母体、别款/点击/缺归因/缺来源/缺购买数证据拒绝。
- HTTP 隔离整合验证已有 Director API 使用注册的商品版本事实，选方向后
  导出摄影关系和购买假设，刷新结果稳定且调用数为零。

## 发现与限制

- 当前真实商品图理解与媒体生成接线未由本轮开放。既有 Live Director
  仍使用现有分析实现；只上传图片而无具体 truth fields 时，购买理由保持待补充。
- 预检是对已编译因果关系、拍摄状态和已知矛盾的有界文本规则，不是开放式
  大模型语义裁判，也不证明图像物理真实性、产品保真或购买转化。
- 新因果关系属于 proposed guidance，不把推导的重心、受力或光影当照片观察事实。
- 有范围的购买记录来自冻结的用户确认资料，未独立审计投放平台；
  脚本适配不等于因果性转化提升，不输出 ROI 提升结论。
- 买点反事实仅用于创作建议，不新增购买理由硬门或审批状态。
- 未修改前端源码、交互或依赖；未重新进行浏览器视觉/人工接受、模型 A/B
  或真实投放验收，本轮不把后端文本测试称为这些验收通过。

## 源码同步

- 本轮七个源码/测试文件入场基线与实际 main 工作目录对应文件已比较；
  六个已有源码基线一致，新增测试独立同步。
- main 源码同步及独立复验成功。七个源码/测试文件与两份本轮文档逐一核对，
  除两侧原有 LF/CRLF 行尾约定外内容一致；没有统一改写行尾。
- 保留两侧已有服务恢复、CHANGELOG 和其他未提交/未跟踪内容。
- 不同步 ZIP、密钥、真实 `.env`、缓存、临时测试数据库或生成媒体。
- 源码同步不等于部署；未重启服务、迁移、付费调用或生产数据写入。

## 下一步

- 用已登记具体商品事实的 SKU 人工核对生成指令及一个购买理由。
- 另行授权同 SKU、同模型与设置的图片 A/B，分别评价摄影真实感、
  商品保真与景别遵从；购买效果留到有可比较投放数据时验证。
