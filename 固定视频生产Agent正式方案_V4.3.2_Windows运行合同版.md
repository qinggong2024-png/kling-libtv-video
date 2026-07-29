# 固定视频生产 Agent 工具——正式方案 V4.3.2（Windows 运行合同版）

> 修订日期：2026-07-26  
> 适用范围：约 10 名内部用户、每天约 100 套父任务；每套默认生成稳定版和动态版各 1 条视频。  
> 版本基线：LibTV CLI 1.1.1。部署时以实际 `--help`、在线模型目录和实时 schema 为执行依据。  
> 文档定位：产品需求、技术架构、开发合同、测试合同、部署合同和上线验收基线。  
> 替代关系：本文取代 V4.3.1 及更早版本，作为后续开发、测试、灰度和上线的唯一实施基线。V4.3.1 原文保留用于变更追溯。
> 本次冻结：只接收 1–7 张有序分镜图；允许明确切镜；9–11 秒均可交付；积分按 Asia/Shanghai 日切；不生成 ZIP；上传素材成功物化到 LibTV 后删除，生成视频在服务器保留 7 天并支持从 LibTV 远程项目找回；第一期采用纯 Web、系统内置邀请制账号、Tailscale 私网远程访问和 Windows 原生 Runner Service，Linux systemd 作为兼容扩展而非上线前置条件。

---

## 一、产品定位

本系统是一个专事专用的视频自动化生产 Agent。

它围绕固定的视频生产流程执行明确、有限、可预测的动作：

1. 接收并整理 1–7 张有序分镜图和用户要求；
2. 完成本地校验、排序、去重和缓存匹配；
3. 使用一次主要多模态调用完成服装识别、分镜理解、一致性判断和两版视频方案生成；
4. 通过固定脚本组装最终提示词和 LibTV 节点参数；
5. 调用 LibTV CLI 完成画布分配、素材上传、节点创建、连接、提交和等待；
6. 自动下载视频并执行本地质量检查；
7. 整理稳定版、动态版和检查结果并交付用户。

系统采用“确定性生产壳 + 嵌入式大模型”的实现方式：

- 大模型专注于视觉理解、语义判断和提示词内容生成；
- 固定脚本负责文件处理、任务调度、参数计算、CLI 操作、状态等待、下载和检查；
- PostgreSQL 保存所有付费命令、状态、积分和远程身份；
- 前端只展示用户可理解的生产阶段和可执行动作。

本系统不建设开放式工具选择、通用任务规划、多 Agent 协作或自由执行能力。所有生产步骤由预定义工作流驱动，大模型输出只作为工作流中的结构化输入。

---

## 二、目标与优先级

### 2.1 第一目标：提高视频生产速度

系统以视频吞吐量和端到端完成时间作为第一优先级：

- 保持 LibTV 生成槽持续有可提交任务；
- 让分析、物化、生成、下载和检查并行执行；
- 减少人工等待和重复操作；
- 缓存可复用结果；
- 将固定动作交给脚本快速执行；
- 将下载和质量检查与新的生成任务解耦。

### 2.2 第二目标：稳定完成付费生产

系统需要稳定保证：

- 同一生成意图只提交一次；
- 素材顺序和父任务归属准确；
- 用户之间的画布与素材保持隔离；
- 生成状态、下载状态和可交付状态分别记录；
- 状态不确定时优先对账，再决定后续动作；
- 个人每日积分额度得到原子保护。

### 2.3 第三目标：降低人工介入

正常任务自动完成：

```text
上传 → 分析 → 自动确认或批量确认 → 准备 → 生成 → 下载 → 检查 → 交付
```

人工主要处理：

- SKU 明显不一致；
- 关键文字或 Logo 无法确认；
- LibTV 远程状态不确定；
- schema 或账号能力发生不兼容变化；
- 成品出现需要业务判断的质量问题。

### 2.4 第四目标：减少模型等待和 Token 消耗

Token 优化服从生产速度：

- 正常任务优先一次主要多模态调用；
- 分镜服装事实和完整任务结果优先缓存；
- 固定计算、校验和最终模板拼装由脚本完成；
- 本地视频技术检查优先于 AI 审查；
- 只有信息不足的字段进入补充分析。

---

## 三、核心成功指标

指标按以下优先级监控：

| 优先级 | 指标 | 说明 |
| --- | --- | --- |
| P0 | 每小时完成视频数 | 核心生产指标 |
| P0 | 生成槽利用率 | 有积压时目标保持高利用率 |
| P0 | 父任务端到端 p50/p95 | 从上传完成到可交付 |
| P0 | 重复正式提交数 | 目标为 0 |
| P0 | 跨任务素材连接数 | 目标为 0 |
| P1 | PREPARED 队列深度 | 保证生成槽有任务可取 |
| P1 | AI 分析 p50/p95 | 判断智能环节是否成为卡点 |
| P1 | 远程物化 p50/p95 | 判断 CLI 准备环节是否成为卡点 |
| P1 | 下载完成延迟 | 生成成功到本地可用的时间 |
| P1 | UNKNOWN 比例 | 状态不确定导致的效率损失 |
| P1 | 人工介入率 | 自动生产覆盖能力 |
| P2 | 缓存命中率 | 减少重复分析和上传 |
| P2 | 单套模型 Token | 成本辅助指标 |
| P2 | 单条视频积分 | 付费成本指标 |

---

## 四、范围与第一期边界

### 4.1 第一期开启的能力

- Web 批量上传；
- 1–7 张有序分镜图；
- 稳定版和动态版各生成 1 条；
- 一次主要多模态分析；
- 分镜服装事实缓存和完整任务缓存；
- 批量确认和可信预设自动确认；
- LibTV CLI 自动物化、提交、等待和下载；
- 个人每日 5,000 积分额度；
- 本地技术质量检查；
- 风险任务和抽样任务的轻量 AI 审查；
- 管理员对账、隔离画布和积分调整；
- 状态、日志和审计查询。

第一期产品与接入边界：

- 仅提供网页系统，不在用户电脑安装业务客户端或本地文件代理；
- 使用系统内置账号，管理员邀请开通，不开放自主注册；
- 稳定版和动态版分别直接下载，不生成、不保存 ZIP；
- 普通用户在局域网内使用局域网地址，远程授权用户通过 Tailscale 私网访问；
- 不使用 Tailscale Funnel 或 Exit Node，不向公网公开系统。

### 4.2 后续版本能力

以下能力保留接口和数据，不进入第一期开发主路径：

- 投放数据闭环；
- 自动学习提示词策略；
- 多模型自动路由；
- 可视化规则编辑器；
- 自动 AIMD 并发调节；
- WDRR 等复杂调度；
- 多主机 Runner 高可用；
- 通用 Agent 工具调用；
- 多 Agent 协作。

---

## 五、总体架构

第一期采用模块化单体，减少部署与排障复杂度。

```text
Web 前端
   ↓
FastAPI 应用
   ├── 任务与素材 API
   ├── 确认与管理 API
   ├── 工作流编排模块
   ├── AI Adapter
   ├── Model Registry
   ├── LibTV CLI Adapter
   ├── 对账模块
   └── 下载与质量检查模块

基础设施
   ├── PostgreSQL：唯一事实源
   ├── MinIO：临时输入、7 天输出、日志与检查证据
   ├── Redis：后续可选，用于通知和短期缓存，第一期不作为核心依赖
   └── Runner Supervisor：管理长时间 LibTV CLI 进程
```

### 5.1 部署单元

第一期只部署三个应用进程类型：

1. **API 服务**：用户接口、管理员接口、SSE；
2. **Worker 服务**：预处理、AI、物化、调度、对账、下载、检查；
3. **Runner Supervisor**：作为 Windows 原生服务独立运行正式 `libtv.exe node --run`；通过 Execution Backend 接口保留未来 Linux systemd 实现。

Model Registry、下载、对账和质量检查是代码模块和任务类型，不拆成独立微服务。

第一期允许 API、Worker 与数据库采用 Windows 原生进程或容器运行；正式 LibTV Runner 必须运行在 Windows 宿主机，直接调用官方 `libtv.exe`，不得把 Windows CLI 放入 Linux 容器或依赖 WSL 转发付费命令。

### 5.2 事实源

- PostgreSQL 是任务、命令、状态、积分和审计的唯一事实源；
- PostgreSQL 驱动队列、Outbox 和 Lease；Redis 不作为第一期核心依赖，后续引入时只承担通知、缓存或唤醒；
- SSE 只传递状态变化通知；
- LibTV 远程读取结果作为对账证据；
- MinIO 是第一期临时对象存储，数据卷落在 Windows `F:` 盘；上传素材成功物化到 LibTV 后删除，成品保留 7 天，日志和检查产物按保留策略清理。

---

## 六、五段并行生产流水线

系统按阶段并行处理不同任务：

```text
阶段 A：本地预处理
阶段 B：AI 分析与提示词准备
阶段 C：LibTV 远程物化
阶段 D：视频生成
阶段 E：下载与质量检查
```

同一时间可以出现：

```text
任务 A 正在生成
任务 B 正在上传和连接节点
任务 C 正在执行 AI 分析
任务 D 正在完成本地校验
任务 E 正在下载和检查
```

### 6.1 流水线并发基线

```yaml
pipeline_concurrency:
  local_preprocess: 20
  ai_analysis: 8
  materialization_global: 6
  materialization_per_project: 1
  generation_same_project: 4
  generation_per_user: 6
  generation_global: 12
  download: 4
  technical_validation: 2
  ai_validation: 2
```

以上为受控生产默认值。实际值通过压测调整。

### 6.2 生成槽补给原则

只要存在任务积压，系统应保持：

```text
PREPARED 可提交数量 ≥ 当前空闲生成槽数量
```

第一期使用明确的队列水位，避免生成槽断粮，也避免提前物化过多远程节点：

```yaml
prepared_queue:
  low_watermark: 12
  high_watermark: 24
```

调度规则：

- 低于 12 条时，优先补充 AI 分析和远程物化能力；
- 12–24 条时，按正常流水线节奏准备；
- 达到 24 条时，暂停继续扩大远程物化，只保留本地预处理和必要分析；
- 当生成槽增加或队列快速下降时自动恢复物化；
- 水位值属于运行配置，可在压测后版本化调整。

当 PREPARED 队列不足时，监控系统优先标记实际卡点：

- AI 分析不足；
- 确认等待；
- 画布封板等待；
- 物化过慢；
- schema 刷新阻塞；
- 用户积分不足。

### 6.3 各阶段解耦

- 下载失败只进入下载重试，不重新生成；
- 质量检查排队不占用生成槽；
- 某个画布异常只隔离该画布；
- 某个用户额度不足不影响其他用户；
- AI 服务短暂降速时，已准备任务继续生成；
- LibTV 生成拥堵时，系统继续预处理和分析后续任务，但控制 PREPARED 上限避免远程节点堆积。

---

## 七、LibTV 资源映射

```text
LibTV workspace
└── 生产工作区

LibTV project
└── 用户的一个生产批次画布

LibTV group
└── 一套父任务

LibTV image node
└── 一张按用户确认顺序参与生成的分镜图

LibTV video node
└── 一个稳定版或动态版生成节点
```

每套父任务默认包含：

- 1 个 group；
- 1–7 个分镜图片节点；
- 1 个稳定版视频节点；
- 1 个动态版视频节点；
- 两个独立 generation attempt。

同一父任务的稳定版和动态版可以连接同一组分镜图片节点。第一期不跨父任务复用 LibTV 图片节点，即使图片 SHA-256 相同，也为新父任务创建独立远程节点，以降低串线、恢复和审计复杂度。

正式生产按目标视频节点执行 `node --run`。系统统一通过 nodeKey 定位远程资源。

## 八、任务输入合同

### 8.1 父任务输入

```json
{
  "clientTaskId": "client-stable-id",
  "storyboards": [
    {"assetId": "A1", "order": 1, "required": true}
  ],
  "userRequirement": "可选补充要求",
  "generationPreset": "DEFAULT_10S_9X16",
  "variants": ["STABLE", "DYNAMIC"]
}
```

### 8.2 素材范围

- 每套父任务只接收分镜图，不单独接收产品图；
- 分镜图：1–7 张；
- 分镜顺序由用户确认；
- 每张分镜图同时用于 AI 分析和 LibTV 生成；
- 每张图片拥有唯一 assetId、版本号和 SHA-256；
- `required=true` 的分镜必须进入最终生成参考集合；
- 第一阶段所有有效分镜默认均为 required；后续只有业务明确需要“可选分镜”时才开放修改。

### 8.3 实时 schema 与媒体数量

本地合同的业务上限是 7 张，最终允许数量取以下两者中的较小值：

```text
allowedStoryboardCount = min(7, realtimeSchema.maxMediaCount)
```

- 实时 schema 支持 1–7 张时，正常执行；
- 实时 schema 临时收紧且当前任务超限时，进入 `SYSTEM_BLOCK` 并要求用户减少分镜；
- 系统不静默删除、替换或重排用户分镜；
- 最终媒体顺序必须与确认版本完全一致，并在提交前回读校验。

## 九、本地预处理

本地脚本完成：

1. 扩展名、MIME 和文件魔数校验；
2. 图片完整性和像素范围校验；
3. EXIF 方向归一化；
4. 去除非必要元数据；
5. SHA-256 计算；
6. 当前任务内重复素材识别；
7. 同批次重复上传识别；
8. 缩略图和分镜联系表生成；
9. 可选 OCR 初检；
10. 分镜序号和父任务归属校验。

### 9.1 处理产物

```json
{
  "assetId": "A1",
  "sha256": "...",
  "normalizedObjectKey": "inputs/.../A1.jpg",
  "thumbnailObjectKey": "thumbs/.../A1.jpg",
  "width": 1080,
  "height": 1920,
  "mimeType": "image/jpeg",
  "order": 1,
  "version": 1
}
```

### 9.2 去重规则

- 同一父任务内完全相同文件只保留一个有效版本，并提示用户检查分镜顺序；
- 本地对象、缩略图和 AI 事实缓存可以按 Hash 复用；
- 同一父任务的稳定版和动态版可以复用该父任务已经验证的远程图片节点；
- 第一阶段不跨父任务复用 LibTV 图片节点；
- 用户之间始终保持独立远程节点；
- 下载结果使用 SHA-256 校验对象完整性。

## 十、AI 分析设计

### 10.1 调用原则

第一期 AI Adapter 使用 OpenAI Platform API Key、Responses API 和结构化 JSON 输出，主模型固定为 `gpt-5.6-sol`。密钥只通过部署环境或本地 `.env` 注入，不写入仓库；正式接入前必须以真实 API 请求验证账号对该模型的权限。默认不启用 Pro、持久化推理、Programmatic Tool Calling 或多 Agent beta，新增能力须单独评估和验证。

普通任务使用一次主要多模态调用完成：

1. 从全部分镜中提取服装和商品视觉事实；
2. 理解每张分镜的人物、场景、动作和构图；
3. 观察不同分镜之间的人物、服装、文字、Logo、场景和商品结构是否存在冲突；
4. 生成稳定版镜头方案；
5. 生成动态版镜头方案；
6. 规范化用户要求；
7. 输出风险标志、未知字段和证据分镜。

AI 不直接输出最终 `PASS / WARNING / QUALITY_REVIEW / SYSTEM_BLOCK`。一致性等级由固定程序根据 AI 观察、OCR、文件校验、实时 schema 和用户预设统一裁决。

调用流程：

```text
缓存命中
→ 直接复用

缓存未命中
→ 一次主要调用
→ JSON Schema 校验
→ 程序计算一致性等级并生成精确计划

关键字段缺失
→ 只补充相关字段一次
→ 仍无法确认时进入人工确认
```

### 10.2 模型输入

输入优先使用：

- 1–7 张分镜组成的联系表；
- 服装文字、Logo、印花或结构不清晰时对应的原始分镜局部；
- 用户补充要求；
- 当前模型和模板版本；
- 任务时长、画幅和稳定/动态目标。

原始大图按需补充，避免重复上传所有高分辨率图片。

### 10.3 精简结构化输出

```json
{
  "schemaVersion": "2.1",
  "garmentFacts": {
    "category": "",
    "mainColor": "",
    "secondaryColor": "",
    "print": "",
    "logo": "",
    "text": "",
    "fit": "",
    "frontSellingPoints": [],
    "backSellingPoints": [],
    "unknownFields": []
  },
  "storyboardFacts": [
    {
      "assetId": "A1",
      "order": 1,
      "scene": "",
      "framing": "",
      "pose": "",
      "actionCandidates": [],
      "interactionObjects": [],
      "productVisibility": "front_clear",
      "shotFunction": "product_opening"
    }
  ],
  "consistencyObservations": {
    "reasonCodes": [],
    "summary": "",
    "unknownFields": [],
    "evidenceAssetIds": []
  },
  "riskFlags": [],
  "stablePlan": {
    "continuityStrategy": "explicit_cuts",
    "shots": [
      {
        "referenceAssetIds": ["A1"],
        "durationWeight": 4,
        "action": "",
        "camera": "",
        "productDisplay": "",
        "shotFunction": ""
      }
    ]
  },
  "dynamicPlan": {
    "continuityStrategy": "explicit_cuts",
    "shots": []
  },
  "userRequirementNormalized": "",
  "modelVersion": ""
}
```

### 10.4 脚本后处理

AI 输出后，固定脚本完成：

- JSON Schema 校验；
- 一致性等级的唯一裁决；
- exact timeline 计算；
- durationWeight 归一化；
- required 分镜覆盖；
- 镜头开始和结束时间；
- A/B 差异检查；
- modeType 选择；
- 分镜节点角色和顺序绑定；
- 正向约束模板拼装；
- 字符预算压缩；
- 最终 JSON 和哈希冻结。

### 10.5 风险标志

模型输出可观察标志，由代码映射风险等级：

```text
TEXT_OR_LOGO_KEY_SELLING_POINT
GARMENT_PARTIALLY_OCCLUDED
STORYBOARD_GARMENT_CONFLICT
STORYBOARD_IDENTITY_CONFLICT
MULTIPLE_PEOPLE
BACK_VIEW_REQUIRED
LOW_DETAIL_REFERENCE
LARGE_POSE_CHANGE
SCENE_DISCONTINUITY
```

代码根据标志、OCR、未知字段、证据分镜、实时 schema 和用户预设生成 `PASS / WARNING / QUALITY_REVIEW / SYSTEM_BLOCK`。AI 的自然语言总结只作为证据，不直接覆盖程序裁决。

### 10.6 调用预算

普通父任务默认：

```yaml
ai_budget:
  primary_analysis_calls: 1
  targeted_repair_calls: 1
  output_validation_calls: 0
  output_validation_sampled_calls: 1
```

`output_validation_calls=0` 表示稳定运行阶段的普通低风险任务只做本地技术检查；上线校准期按第二十八章执行更高比例的轻量 AI 审查。

## 十一、缓存策略

### 11.1 分镜服装事实缓存

缓存键：

```text
有序分镜集合 Hash
+ 视觉模型版本
+ 视觉提取 Schema 版本
```

缓存内容：

- 服装品类；
- 颜色；
- 印花；
- Logo；
- 文字；
- 版型；
- 正背卖点；
- 分镜间冲突观察和未知字段。

提示词模板升级不使视觉事实缓存失效。因为没有独立产品图，只有有序分镜集合完全相同或命中经人工确认的事实版本时才直接复用。

### 11.2 人工确认缓存

缓存键：

```text
分镜视觉事实 Hash + 人工修订版本
```

人工修订后的服装事实在相同有序分镜集合中优先使用。人工修订必须保留原始模型输出、修改人、修改原因和版本号。

### 11.3 完整任务缓存

缓存键：

```text
全部分镜 Hash
+ 分镜顺序
+ 用户要求 Hash
+ AI 模型版本
+ 分析 Schema 版本
+ 生成模板版本
+ 生成配置 Hash
```

完全相同任务可以直接复用：

- 分析结果；
- 稳定版方案；
- 动态版方案；
- 最终提示词；
- 程序裁决的一致性等级。

远程节点和付费 generation attempt 不跨父任务复用；再次生成仍创建新的节点和 attempt。

## 十二、一致性与确认级别

### 12.1 唯一裁决原则

一致性等级由程序统一计算并保存。输入包括：

- AI 输出的 `consistencyObservations`；
- `riskFlags` 和 `unknownFields`；
- OCR 结果；
- 分镜文件和顺序校验；
- 实时 schema 与账号能力；
- 用户可信预设。

AI 不能直接写入最终等级；人工确认可以创建新的裁决版本，但不能覆盖历史记录。

由于系统不接收独立产品图或外部 SKU 真值，本章的一致性只表示“上传的各张分镜之间是否一致”。它不能证明分镜中的服装与某个外部商品库、实物 SKU 或投放商品绝对一致。后续如需验证外部 SKU，需要新增明确的商品真值输入或商品库接口，不能复用当前等级冒充外部校验。

### 12.2 PASS

不同分镜中的人物、服装品类、颜色、核心印花、Logo、文字、结构和主要场景身份一致，任务可进入快速路径。

### 12.3 WARNING

存在自然褶皱、轻微遮挡、透视、环境光或动作姿态差异，但整体人物与商品身份清晰。可信预设可以自动继续。

### 12.4 QUALITY_REVIEW

分镜之间存在 SKU、人物、印花、文字、Logo、品类、结构或场景身份差异的可能，需要用户查看证据分镜后确认。具有权限的用户可以接受风险继续生产。

### 12.5 SYSTEM_BLOCK

系统当前无法可靠执行，例如：

- 输入文件或数量不符合实时 schema；
- 模型权限、账号余额或参数不可用；
- 远程画布、节点或声音字段存在冲突；
- 当前 attempt 已进入 UNKNOWN；
- 远程身份无法唯一确认。

该级别进入系统处理或管理员对账。

## 十三、提示词生成合同

### 13.1 设计原则

最终提示词由：

```text
AI 生成的语义方案
+ 固定正向模板
+ 脚本计算的时间轴
+ 有序分镜节点引用
+ 少量任务修正约束
```

组成。

提示词重点描述“希望画面如何稳定完成”，减少长篇否定词和通用禁止项。

### 13.2 固定结构

```text
1. Ordered storyboard reference roles
2. Garment and identity lock
3. Shot timeline
4. Movement and camera behavior
5. Product presentation
6. Continuity guidance
7. User requirement
8. Task-specific corrections（可选，最多 3 条）
```

### 13.3 正向公共约束

推荐使用以下语义：

```text
Keep the same model, garment, print, logo, text, colors and scene identity throughout.
Preserve the garment's original proportions and visible fabric structure.
Keep the main product area clear during the key display moments.
Use natural body mechanics and smooth camera movement.
Maintain a coherent background and continuous lighting.
Use only the garment's original typography and branding.
```

### 13.4 稳定版

稳定版强调：

- 小幅自然动作；
- 清晰商品展示；
- 平稳运镜；
- 正面卖点拥有较长展示时间；
- 背面存在实际卖点时安排背面镜头；
- 动作在镜头结束前自然收束。

默认 10 秒使用 2–3 个镜头。

### 13.5 动态版

动态版强调：

- 更明显的人物位移；
- 更强的广告节奏；
- 跟拍、推进、横移或自然转身；
- 在商品结构稳定的基础上提高动态表现；
- 开场、动作、镜头运动或镜头顺序与稳定版形成明确差异。

默认 10 秒使用 3–4 个镜头。

### 13.6 时间轴生成

AI 输出 `durationWeight`，脚本计算：

```text
shotDuration = totalDuration × weight / sum(weights)
```

脚本保证：

- 第一镜从 0 秒开始；
- 镜头连续覆盖完整时长；
- required 分镜得到体现；
- 关键商品展示获得足够时间；
- 最后一镜结束时间等于节点时长。

### 13.7 A/B 差异

稳定版和动态版至少在以下两项形成差异：

- 首镜功能；
- 主要人物动作；
- 镜头运动；
- 镜头顺序；
- 节奏。

商品身份、人物身份、场景主体和核心卖点保持一致。

### 13.8 字符预算

```yaml
prompt_budget:
  target_min: 900
  target_max: 1300
  extended_max: 1600
  safety_soft_max: 1850
  hard_max: realtime_schema
```

超出目标预算时，脚本按顺序压缩：

1. 合并重复修饰；
2. 删除重复参数表达；
3. 压缩环境描述；
4. 保留素材角色、商品事实、动作、镜头和关键修正。

### 13.9 用户补充要求

用户要求作为独立字段参与模板：

- 保存原始文本；
- 保存规范化文本；
- 保存最终提示词；
- 转义模板控制字符；
- 与素材事实和生成参数分层处理；
- 修改后产生新的版本和哈希。

---

## 十四、默认生成配置

```yaml
generation_preset:
  name: DEFAULT_10S_9X16
  model_display_name: Kling O3
  model_key: kling-v3-omni
  aspect_ratio: "9:16"
  duration_seconds: 10
  quality: high
  sound: off
  smart_storyboard: false
  quantity: 1
```

系统允许稳定版和动态版出现明确切镜：

- 稳定版默认 2–3 镜；
- 动态版默认 3–4 镜；
- `continuityStrategy` 默认 `explicit_cuts`；
- `smart_storyboard` 第一阶段保持关闭，后续仅在真实 A/B 测试证明效果和稳定性更好时启用。

modeType 由实际有序分镜数量和实时 schema 选择：

```text
1 张分镜参考 → 当前快照优先 singleImage2video
2–7 张分镜参考 → 当前快照优先 mixed2video
```

Adapter 根据实时 schema 的 `originalField` 映射最终参数。写入后回读视频节点，确认：

- modelKey；
- modeType；
- quality；
- duration；
- aspect ratio；
- sound；
- media order；
- prompt。

## 十五、Model Registry

### 15.1 职责

集中缓存：

- 模型展示名；
- CLI 接受的模型值；
- modelKey 和 toolKey；
- 参数 schema；
- 媒体数量范围；
- prompt 最大长度；
- 权限和会员要求；
- `originalField` 映射；
- compatibility fingerprint。

### 15.2 刷新策略

```yaml
model_registry:
  soft_ttl_minutes: 10
  hard_ttl_minutes: 30
  refresh_single_flight: true
```

刷新流程：

1. 查询视频模型目录；
2. 读取目标模型详情；
3. 保存 schema 和账号作用域；
4. 计算 compatibility fingerprint；
5. 发布新快照。

以下情况立即刷新：

- CLI 版本变化；
- 模型或参数错误；
- 媒体数量错误；
- 权限或会员状态变化；
- 管理员触发刷新。

### 15.3 提交前兼容性复核

- fingerprint 相同：直接继续；
- 仅新增无关字段：记录新快照并继续；
- 当前参数、素材数量或权限发生变化：回到重新确认；
- schema 超过 hard TTL 且刷新不可用：暂停新的付费提交，已有生成和下载继续运行。

---

## 十六、本地草稿与确认

### 16.1 延迟物化

用户确认前只保存：

- 输入素材与顺序；
- AI 分析；
- 一致性结果；
- 稳定版和动态版方案；
- 最终提示词；
- orderedStoryboardReferenceAssets；
- 参数和 schemaSnapshotId；
- 所有哈希。

用户确认后再创建 LibTV 远程结构。

### 16.2 快速确认

正常任务支持：

- PASS 自动确认；
- 可信预设下 WARNING 自动确认；
- 批量确认；
- 用户明确选择“本批次使用相同默认配置”。

### 16.3 确认冻结对象

```text
analysisResultHash
stablePromptHash
dynamicPromptHash
orderedStoryboardReferenceAssetsHash
generationConfigHash
schemaSnapshotId
promptTemplateVersion
```

素材、顺序、提示词、参数或兼容语义变化时创建新确认版本。

---

## 十七、用户画布模型

### 17.1 结构状态

```text
OPEN
DRAINING
SEALED
QUARANTINED
```

- **OPEN**：接收新父任务和远程物化；
- **DRAINING**：完成已占位任务的物化并准备封板；
- **SEALED**：结构固定，可并行提交已准备视频节点；
- **QUARANTINED**：保留现场并进入只读对账和管理员处理。

每个用户同时拥有：

```text
最多 1 个 OPEN
最多 1 个 DRAINING
多个历史 SEALED / QUARANTINED
```

数据库用部分唯一索引保证该约束。

### 17.2 执行状态

```text
IDLE / QUEUED / RUNNING / PARTIAL / COMPLETED
```

执行状态由子任务聚合计算。

### 17.3 画布容量

```yaml
canvas:
  parent_task_soft_limit: 5
  parent_task_hard_limit: 10
  video_node_soft_limit: 10
  remote_node_soft_limit: 50
  remote_node_hard_limit: 100
  max_storyboards_per_task: 7
```

---

## 十八、容量感知封板

固定等待时间会造成生成槽空闲，因此 V4.3.2 沿用容量感知封板。

### 18.1 默认窗口

```yaml
canvas_sealing:
  grace_seconds_when_slots_idle: 5
  batch_window_seconds: 20
  batch_window_min_seconds: 10
  batch_window_max_seconds: 60
  open_max_minutes: 10
  draining_max_minutes: 10
```

### 18.2 封板条件

满足任一条件时，OPEN 原子转为 DRAINING：

1. 当前存在空闲生成槽，且至少 1 套任务已 PREPARED，5 秒宽限期结束；
2. 第一套 PREPARED 后已等待 20 秒；
3. 父任务达到 5 套软上限；
4. 待生成视频节点达到 10 个软上限；
5. 父任务达到 10 套硬上限；
6. 加急任务请求立即运行；
7. 画布查询或写入出现异常信号；
8. 管理员提前封板。

### 18.3 并行准备新画布

DRAINING 不占用 OPEN 槽。旧画布封板和生成期间，新任务可以进入新的 OPEN 画布并继续准备。

### 18.4 数据库分配事务

父任务分配在同一事务中完成：

1. 锁定用户画布分配行；
2. 查询或创建 OPEN 画布；
3. 检查剩余容量；
4. 写入 parentTask.assignedProjectUuid；
5. 增加占位计数；
6. 根据条件执行 `OPEN → DRAINING` CAS；
7. 提交后启动远程物化。

---

## 十九、远程物化 Saga

LibTV 结构创建由多个 CLI 命令构成，系统使用持久化 Saga 保证可恢复。

### 19.1 确定性远程名称

```text
G-{parentTaskShortId}
IMG-{parentTaskShortId}-{assetOrder}-{assetVersion}
VID-{parentTaskShortId}-STABLE-{attemptSequence}
VID-{parentTaskShortId}-DYNAMIC-{attemptSequence}
```

成功后保存真实 groupNodeKey 和 nodeKey。名称用于恢复查找，nodeKey 用于正式定位。

### 19.2 Operation 状态

```text
PENDING
EXECUTING
RETRYABLE
VERIFIED
WRITE_UNCERTAIN
MANUAL_REVIEW
ABANDONED
```

### 19.3 物化步骤

每个画布同一时间由一个写执行器完成结构写入：

1. 创建或验证 group；
2. 上传或验证生成参考图片节点；
3. 创建稳定版视频节点；
4. 创建动态版视频节点；
5. 写入模型和全部显式参数；
6. 按 orderedStoryboardReferenceAssets 顺序连接图片节点；
7. 回读媒体集合和 order；
8. 写入含节点引用的最终提示词；
9. 绑定 group；
10. 完整回读两个视频节点；
11. 校验参数、输入、顺序、提示词和字段映射；
12. 保存远程身份与回读快照；
13. 两个 attempt 进入 PREPARED。

### 19.4 恢复规则

- 已验证 operation 直接复用；
- 临时网络错误在当前 operation 内有限重试；
- 命令结果不明确时先执行远程只读查询；
- 远程身份唯一且内容一致时标记 VERIFIED；
- 远程状态无法唯一确认时进入 WRITE_UNCERTAIN，并将画布转为 QUARANTINED；
- 管理员基于日志、远程快照和 nodeKey 处理 MANUAL_REVIEW。

### 19.5 结构写并发

- 同一 project：1 个结构写执行器；
- 不同 project：并行物化；
- `node --run` 运行期间不持有 project 结构写锁；
- 新 OPEN 画布可以在旧 SEALED 画布生成期间继续准备。

---

## 二十、LibTV CLI Adapter

业务模块只调用 Adapter 方法：

```text
getModelCatalog()
getModelSchema()
createProject()
createGroup()
uploadImage()
createVideoNode()
setNodeParams()
connectNodes()
setMediaOrder()
setPrompt()
readNode()
runNode()
queryNodeResult()
downloadMedia()
```

Adapter 统一完成：

- 参数数组启动；
- 独立工作目录；
- 独立 HOME / XDG_CONFIG_HOME；
- projectUuid、groupNodeKey、nodeKey 显式传入；
- stdout 和 stderr 分离；
- 退出码解析；
- taskId 捕获；
- 日志脱敏；
- CLI 版本、账号和 teamId 校验；
- 结果映射为内部错误码。

生产期间账号上下文固定。Runner 启动前记录：

```text
cliVersion
accountId
teamId
workspaceId
projectUuid
nodeKey
```

---

## 二十一、Runner Supervisor

### 21.1 目标

正式 `libtv node --run` 是长时间付费进程。Runner Supervisor 保证应用或 Worker 重启时进程仍可被识别和持续观察。

第一期冻结为：

```text
Windows Runner 主机
+ 一个开机自启的 Runner Windows Service
+ 每个 generation command 一个独立 command-host 进程
+ 每个 command-host 前台阻塞运行一个 libtv.exe node --run 子进程
```

Runner Windows Service 只负责领取、启动、发现和恢复 command-host，不在服务主进程内直接执行付费 CLI。每个 command-host：

- 独立工作目录；
- 独立 stdout/stderr 文件；
- 独立受控环境变量和凭据快照；
- 持久 commandHostId、PID、进程启动时间和随机 nonce；
- 将 CLI 终态 JSON、退出码和完成时间原子写入 terminal result 文件；
- 使用显式 `projectUuid`、`groupNodeKey` 和 `nodeKey`，不依赖共享目录中的 `.libtv/project.json`；
- `libtv.exe node --run` 在 command-host 内保持前台阻塞，外层不追加 timeout、不自行轮询生成状态；
- API、Worker 或 Runner Windows Service 重启后，可通过数据库、进程身份和持久文件恢复观察。

command-host 必须与 Runner Windows Service 解耦。Runner Windows Service 异常退出时，不得因为父进程退出而主动终止已经进入 `LAUNCH_STARTED` 的 command-host。command-host 的进程身份至少由以下字段共同确认：

```text
commandHostId
processId
processStartedAt
processNonce
executableHash
commandHash
```

未来如增加 Linux，必须实现同一 `RunnerExecutionBackend` 合同；Windows 使用 `WINDOWS_COMMAND_HOST`，Linux 可使用 `SYSTEMD_TRANSIENT_UNIT`。业务状态机和重复提交保护不得因操作系统不同而分叉。

### 21.2 generation command

正式付费提交先写入 PostgreSQL：

```text
READY
CLAIMED
LAUNCH_STARTED
PROCESS_STARTED
TERMINAL
UNCERTAIN
CANCELLED
```

Runner 只执行已领取且状态匹配的 command。

### 21.3 lease 与心跳

```yaml
runner:
  execution_backend: WINDOWS_COMMAND_HOST
  claim_lease_seconds: 60
  heartbeat_seconds: 15
  command_host_heartbeat_seconds: 15
  launch_confirmation_timeout_seconds: 30
  disk_warn_free_percent: 15
  disk_stop_free_percent: 5
```

规则：

- `CLAIMED` 且 `launchStartedAt` 为空时，lease 过期后可释放并重新领取同一 command；
- 一旦写入 `LAUNCH_STARTED`，不得因 lease 超时而重新执行 `node --run`；
- command-host 创建结果在 30 秒内无法确认时转 `UNCERTAIN`，先查询 Windows 进程、terminal result、日志和 LibTV；
- Runner 每 15 秒更新主机和 command 心跳；
- command-host 每 15 秒更新本地 heartbeat 文件或等价持久证据；
- 可用磁盘低于 15% 告警，低于 5% 暂停创建新 command-host；
- stdout/stderr 无法持久写入时，当前任务按证据转 UNKNOWN 并进入对账。

### 21.4 启动事务

1. Dispatcher 原子领取 READY command；
2. 获取 global/user/project 容量；
3. 复核积分预占；
4. command 进入 CLAIMED；
5. Runner 写入 LAUNCH_STARTED；
6. 生成唯一 commandHostId、工作目录、nonce 和不可变命令清单；
7. Windows Runner Service 启动独立 command-host；
8. command-host 成功启动后写 PROCESS_STARTED、PID、进程启动时间和 attempt RUNNING；
9. command-host 前台运行 `libtv.exe node --run`，持续保存 stdout、stderr、心跳和终态文件；
10. Runner 持续观察 command-host、CLI 进程和 terminal result；
11. 写回 SUCCEEDED、FAILED 或 UNKNOWN。

### 21.5 主机和进程恢复原则

- taskId 是平台受理证据；
- CLI 终态和远程节点结果共同决定最终状态；
- 已进入 LAUNCH_STARTED 的命令按“可能已经提交”处理；
- Worker 或 API 重启不影响 Windows Runner Service 和 command-host；
- Runner Windows Service 重启后，按 commandHostId、PID、进程启动时间、nonce、terminal result 和数据库恢复观察；身份有任何冲突时不得接管或重启付费命令；
- Windows 主机重启后，默认冻结新付费提交，核对数据库、Windows 事件日志、command-host/CLI 日志、terminal result 和 LibTV 远程状态；
- 主机重启前处于 LAUNCH_STARTED、PROCESS_STARTED 或 RUNNING 的命令一律先进入恢复审计，不能仅凭本地进程已消失判定未提交；
- 监控证据中断时转 UNCERTAIN/UNKNOWN 并进入只读对账；
- 同一 nodeKey 保持唯一活动 command；
- 恢复完成前不得创建替代付费 attempt。

### 21.6 Windows 服务合同

- Runner 使用独立的受控 Windows 服务账号运行，不依赖交互式用户登录；
- `libtv.exe` 路径、版本和 SHA-256 在服务启动及每次 launch 前校验；
- LibTV 凭据由 Secret Manager、受控环境变量或服务账号的受控凭据目录提供，不读取普通用户临时会话；
- Windows Service 配置为开机自动启动，并配置服务失败后的有限自动重启；
- Windows 自动睡眠、休眠和自动关机必须关闭；操作系统更新重启进入计划维护流程；
- command-host 和 `libtv.exe` 以参数数组启动，不拼接 shell 命令字符串；
- 工作目录、日志目录和 terminal result 目录使用本机固定绝对路径，并设置服务账号最小权限 ACL；
- 杀毒软件或 EDR 对 CLI、临时视频和日志目录的策略必须在 STAGING 验证，不能直接跳过安全软件；
- 不要求安装 Linux 虚拟机、WSL 或 systemd。

## 二十二、生成并发策略

### 22.1 受控生产默认值

```yaml
generation_concurrency:
  same_project: 4
  per_user: 6
  global: 12
```

此默认值兼顾吞吐与当前规模。正式上线前使用真实平台完成同画布 4、全局 12 的压测。

### 22.2 验证阶梯

```text
开发冒烟：同画布 1 → 2
受控生产：同画布 4，全局 12
扩容验证：同画布 4 → 6 → 8
             全局 12 → 16 → 20
```

### 22.3 容量计算

```text
requiredConcurrency
= ceil(
  每日父任务数 × 每套视频数 × 平均生成分钟数
  ÷ 可用生产分钟数
  ÷ 目标利用率
)
```

目标利用率建议 70%–80%，为突发任务和异常恢复留出空间。

### 22.4 PREPARED 队列联动

生成调度与第六章的水位联动：

```yaml
prepared_queue:
  low_watermark: 12
  high_watermark: 24
```

全局并发调整后，水位至少满足：

```text
low_watermark ≥ generation_global
high_watermark ≥ 2 × generation_global
```

默认全局并发从 12 提升到 16 或 20 时，应同步评估并提高队列水位，避免扩容后出现生成槽断粮。

### 22.5 人工调节

第一期由管理员调节并发配置：

- 全局限流或账号异常：调整 global；
- 单画布查询变慢：调整对应 project；
- 单用户任务过多：由 per_user 上限实现公平；
- 下载拥堵：只调整 download pool；
- AI 分析拥堵：只调整 ai_analysis pool。

自动 AIMD 在积累足够样本后单独评审。

---

## 二十三、公平调度

第一期使用简单、可解释的用户轮询：

1. 同一用户每轮最多领取 2 条；
2. 先在用户之间轮询；
3. 再在用户内部按优先级排序；
4. 加急任务保留比例上限。

用户内部优先级：

1. 等待较久的稳定版；
2. 普通稳定版；
3. 等待较久的动态版；
4. 普通动态版；
5. 用户主动重新生成；
6. 管理员测试任务。

### 23.1 稳定版与动态版

低风险任务：两版同时进入队列。

中高风险任务：稳定版优先；稳定版生成、下载和质量通过后，动态版自动解除依赖。

该策略减少高风险任务连续消耗两次积分，同时不影响低风险任务吞吐。

---

## 二十四、状态机

### 24.1 父任务用户阶段

```text
DRAFT
ANALYZING
AWAITING_CONFIRMATION
PREPARING
WAITING_FOR_SEAL
QUEUED
GENERATING
DOWNLOADING
VALIDATING
PARTIALLY_DELIVERABLE
DELIVERABLE
ACTION_REQUIRED
CANCELLED
```

### 24.2 generation attempt

```text
DRAFT
MATERIALIZING
PREPARED
DISPATCH_PENDING
LAUNCHING
RUNNING
SUCCEEDED
FAILED_BEFORE_SUBMIT
FAILED_TERMINAL
UNKNOWN_AFTER_SUBMIT
NEEDS_MANUAL_REVIEW
CANCELLED_BEFORE_SUBMIT
```

合法主路径：

```text
DRAFT
→ MATERIALIZING
→ PREPARED
→ DISPATCH_PENDING
→ LAUNCHING
→ RUNNING
→ SUCCEEDED
```

异常路径：

```text
MATERIALIZING → FAILED_BEFORE_SUBMIT | NEEDS_MANUAL_REVIEW
LAUNCHING/RUNNING → FAILED_TERMINAL | UNKNOWN_AFTER_SUBMIT
UNKNOWN_AFTER_SUBMIT → RUNNING | SUCCEEDED | FAILED_TERMINAL | NEEDS_MANUAL_REVIEW
```

### 24.3 状态更新

所有状态迁移使用 CAS：

```sql
UPDATE generation_attempt
SET status = :new_status,
    state_version = state_version + 1,
    updated_at = now()
WHERE id = :id
  AND status = :expected_status
  AND state_version = :expected_version;
```

更新行数为 0 时重新读取最新状态。

### 24.4 生成、下载和验证正交状态

```text
generationStatus:
PENDING / RUNNING / SUCCEEDED / FAILED / UNKNOWN

downloadStatus:
NOT_READY / QUEUED / DOWNLOADING / READY / FAILED

validationStatus:
NOT_READY / TECHNICAL_CHECKING / AI_CHECKING /
PASSED / WARNING / FAILED / MANUAL_REVIEW
```

父任务聚合规则：

```text
至少一个版本可交付，另一个尚未可交付
→ PARTIALLY_DELIVERABLE

两个请求版本均可交付
→ DELIVERABLE

没有版本可交付，且需要用户或管理员动作
→ ACTION_REQUIRED
```

稳定版和动态版按各自可交付状态提供独立下载；系统不创建聚合 ZIP。

---

## 二十五、幂等与重复提交保护

### 25.1 API 幂等

所有产生副作用的 API 接受 `Idempotency-Key`。

唯一约束：

```text
UNIQUE(tenant_id, operation_type, idempotency_key)
```

规则：

- 同 key、同 payload 返回首次响应；
- 同 key、不同 payload 返回 409；
- 网络结果不明时客户端重用原 key；
- 重新生成使用新 key、新 variant、新 node 和新 attempt。

### 25.2 生成意图 Hash

intent hash 包含：

- userId、parentTaskId、variant；
- projectUuid、groupNodeKey、nodeKey；
- modelKey、schema fingerprint；
- 输入素材 nodeKey、角色和顺序；
- stable/dynamic prompt hash；
- 全部生成参数；
- 素材和提示词版本。

数据库约束：

```text
UNIQUE(generation_command.attempt_id)
同一 projectUuid + nodeKey 最多一个活动 attempt
同一 intent_hash 在活动或成功范围内唯一
```

### 25.3 正式提交保护

- generation command 是正式付费命令；
- Worker 内存消息只用于唤醒；
- Runner 领取使用 `FOR UPDATE SKIP LOCKED`；
- 同一 nodeKey 的 submit lock 在数据库中实现；
- UNKNOWN 状态先对账，再由管理员或用户创建新付费版本。

### 25.4 取消合同与竞争处理

取消动作以服务端 `actionCapabilities.canCancel` 和数据库 CAS 为准：

```text
DRAFT / ANALYZING / AWAITING_CONFIRMATION
→ 直接取消本地任务

MATERIALIZING
→ 停止尚未开始的 operation，保留已创建远程身份供清理或复用

PREPARED / DISPATCH_PENDING
→ 在 generation command 尚未进入 LAUNCH_STARTED 时取消

LAUNCHING / RUNNING / UNKNOWN_AFTER_SUBMIT
→ 返回“任务已进入提交或生成阶段”，保留原进程和对账流程
```

取消与 Dispatcher 领取同时发生时：

1. 取消方和领取方使用同一 attempt 行与 stateVersion；
2. 取消 CAS 先成功：command 进入 CANCELLED，Dispatcher 跳过；
3. Dispatcher 先进入 LAUNCH_STARTED：取消返回当前真实阶段；
4. 前端隐藏任务或消息队列撤销不改变正式 command；
5. 已生成文件仍按数据保留策略可查询和下载。

---

## 二十六、积分额度与账本

### 26.1 额度规则

```yaml
points_policy:
  daily_user_limit: 5000
  team_limit: null
  business_timezone: Asia/Shanghai
  prelaunch_stale_minutes: 120
```

个人当日视图：

```text
consumed_points
reserved_points
uncertain_points
remaining_points = 5000 - consumed_points - reserved_points - uncertain_points
```

### 26.2 原子预占

确认执行并入队时，在一个事务中完成：

1. 按 `Asia/Shanghai` 计算预占发生时的 businessDate；
2. 锁定 userId + businessDate 汇总行；
3. 校验个人剩余额度；
4. 复核 LibTV 主账号剩余积分；
5. 锁定 attempt；
6. 创建 points reservation；
7. 创建 generation command；
8. 写 Outbox 和审计事件；
9. 提交事务。

跨日完成的任务仍计入预占发生时所属的上海业务日，不因生成完成时间跨零点而迁移账本。

### 26.3 扣费证据与结算来源

每个 attempt 保存：

```text
chargeStatus:
NOT_CHARGED / CHARGED / UNKNOWN

billingSource:
TASK_BILLING / PRICE_SNAPSHOT / ISOLATED_BALANCE_DELTA / MANUAL
```

结算证据优先级：

1. LibTV 可归属到该 taskId 或 nodeKey 的单任务实际积分记录；
2. 实时 schema 或模型价格快照提供固定、确定且经回读确认的单次积分；
3. 仅在没有其他并发付费命令的隔离窗口，使用账号余额差值；
4. 管理员根据平台账单执行人工调整。

普通并发生产中不得使用主账号余额前后差值直接分摊到单条视频。预估值只用于预占；缺少可归属的结算证据时保持 `UNKNOWN`，不得伪装成精确实际消耗。

### 26.4 生命周期

```text
确认预检：ESTIMATED
确认执行：RESERVED
运行完成且扣费证据明确：SETTLED
明确未提交或未扣分：RELEASED
扣分结果待核对：UNCERTAIN
人工修正：ADJUST 分录
```

账本采用只追加方式。实际扣分高于预估时完整记录，并暂停该用户当日后续新任务，直到额度恢复或管理员调整。

### 26.5 预占超时与释放

- command 在 120 分钟内仍未进入 `LAUNCH_STARTED`，且不处于正在执行的物化 operation，可取消 command 并释放预占；
- 已进入 `LAUNCH_STARTED`、已经捕获 taskId 或远程状态不明确的任务，积分不得自动释放；
- `FAILED_TERMINAL` 只有在 `chargeStatus=NOT_CHARGED` 时才释放；
- `chargeStatus=CHARGED` 时结算实际积分；
- `chargeStatus=UNKNOWN` 时进入 UNCERTAIN，对账或人工处理后再结算。

### 26.6 日切

按 `Asia/Shanghai` 的 businessDate 计算个人额度。历史账本永久保留，不覆盖旧日数据。

## 二十七、重试与对账

### 27.1 可自动重试的固定操作

在明确尚未进入正式付费提交时，可以有限重试：

- 本地预处理；
- AI 网络请求；
- JSON 结构修复；
- schema 刷新；
- 远程素材上传；
- 未提交节点参数写入；
- 下载；
- 本地质量检查。

推荐：

```yaml
retry_policy:
  preprocess_max: 2
  ai_primary_max: 1
  ai_targeted_repair_max: 1
  materialization_operation_max: 3
  download_max: 5
  validation_max: 2
```

### 27.2 付费提交后的处理

当 `launchStartedAt` 已写入、进程可能已创建、taskId 已捕获或远程状态无法确认时：

```text
attempt → UNKNOWN_AFTER_SUBMIT
command → UNCERTAIN
points reservation → UNCERTAIN
```

Reconciliation Worker 只读查询：

- node taskInfo；
- 远程运行状态；
- 视频 URL；
- poster；
- 输出节点；
- taskId。

可确认时自动归类为 RUNNING、SUCCEEDED 或 FAILED_TERMINAL，并同步更新 `chargeStatus`。连续对账仍无法确认时进入人工处理。

自动创建替代 attempt 的前提必须同时满足：

- 原 attempt 已是明确终态；
- `chargeStatus=NOT_CHARGED`；
- 原 nodeKey 不存在活动或成功结果；
- 新 attempt 使用新的 idempotency key、node 和 intent version。

任何 `UNKNOWN` 或 `chargeStatus=UNKNOWN` 的任务都不得自动重新提交。

### 27.3 对账节奏

```yaml
reconciliation:
  initial_delay_seconds: 30
  intervals_seconds: [30, 60, 120, 300, 600]
  max_automatic_window_minutes: 60
```

---

## 二十八、下载与质量检查

### 28.1 下载

生成成功后立即创建下载任务。下载池与生成池独立。

流程：

1. 获取有效视频 URL；
2. 流式下载到临时文件；
3. 计算 SHA-256；
4. 校验容器和视频流；
5. 上传对象存储；
6. 写 download artifact；
7. 生成短期签名下载 URL。

文件命名：

```text
{businessDate}_{userShortId}_{parentTaskShortId}_{variant}_v{revision}.mp4
```

### 28.2 本地技术检查

全量执行：

- 视频可解码；
- 实际时长；
- 画幅比例；
- 分辨率；
- 意外音轨；
- 黑帧；
- 长时间冻结帧；
- 严重花屏或文件截断。

10 秒预设的时长合同：

```text
9.0–11.0 秒 → PASSED，可正常交付
< 9.0 秒或 > 11.0 秒 → FAILED
```

系统可以额外记录与 10 秒目标的偏差，但 9–11 秒之间不产生质量警告，也不阻止交付。

工具：

```text
ffprobe
ffmpeg
OpenCV（可选）
```

### 28.3 轻量 AI 审查

AI 输入为抽取帧联系表和最少元数据，不上传完整视频。输出：

```json
{
  "status": "PASS|WARNING|MANUAL_REVIEW",
  "issueCodes": [],
  "evidenceFrames": [],
  "summary": ""
}
```

AI 结论用于转人工和记录，不直接触发新的付费生成。

上线校准期按以下比例执行：

```text
前 200 条真实视频：全部执行轻量 AI 审查
累计 200–500 条：高风险 100%，低风险随机 20%
累计超过 500 条且漏检率稳定：高风险 100%，低风险随机 10%
```

高风险包括：

- QUALITY_REVIEW 任务；
- 文字、Logo 或复杂转身任务；
- 本地检查出现可疑信号；
- 程序规则命中强制审查条件。

AI 审查目标 p95 不超过 60 秒。审核与生成解耦；已完成技术检查的视频可以显示“视觉审核处理中”。

### 28.4 可交付规则

```text
可交付 = generation SUCCEEDED
       + download READY
       + technical validation PASSED
       + AI validation PASSED/WARNING（仅适用于本任务被选入 AI 审查时）
```

`MANUAL_REVIEW` 需要业务人员确认。稳定版与动态版分别判断，一个版本通过即可先交付该版本。

### 28.5 从 LibTV 远程项目找回

上传素材成功物化到 LibTV 后从服务器对象存储删除；生成视频默认保留 7 天。对象删除后，数据库继续保留：

- projectUuid；
- groupNodeKey；
- videoNodeKey；
- taskId；
- 远程结果身份；
- 文件 Hash 和原始文件名；
- 积分和审计记录。

用户可以发起“从 LibTV 远程项目找回”：

1. 系统只读查询原 videoNodeKey；
2. 远程视频仍存在时，重新下载、校验并写入新的 download artifact revision；
3. 找回属于重新下载，不创建 generation attempt，不消耗生成积分；
4. 远程结果已失效时明确提示无法找回；
5. 系统不得把“找回失败”自动转换成付费重新生成。

## 二十九、API 合同

### 29.1 端点基线

```text
POST /uploads
POST /batches
POST /tasks
PATCH /tasks/{id}
GET  /tasks
GET  /tasks/{id}
POST /tasks/{id}/analyze
POST /tasks/{id}/confirm
POST /confirmations/preflight
POST /confirmations/execute
POST /tasks/{id}/cancel
POST /tasks/{id}/accept-risk
POST /tasks/{id}/regenerate
POST /tasks/{id}/restore-remote-output
POST /downloads
GET  /events

POST /admin/reconciliations/{id}/classify
POST /admin/canvases/{id}/quarantine
POST /admin/canvases/{id}/release
POST /admin/model-registry/refresh
POST /admin/points/adjustments
PATCH /admin/runtime-config
```

### 29.2 任务响应

```json
{
  "id": "task-id",
  "phase": "QUEUED",
  "phaseReasonCode": "WAITING_FOR_CAPACITY",
  "nextStep": "系统将自动开始",
  "stateVersion": 17,
  "updatedAt": "2026-07-26T10:00:00+08:00",
  "estimatedPoints": 120,
  "pointsQuota": {
    "dailyLimit": 5000,
    "consumed": 1800,
    "reserved": 1200,
    "remaining": 2000,
    "teamLimit": null
  },
  "variants": {
    "stable": {
      "generationStatus": "RUNNING",
      "downloadStatus": "NOT_READY",
      "validationStatus": "NOT_READY"
    },
    "dynamic": {
      "generationStatus": "PENDING",
      "downloadStatus": "NOT_READY",
      "validationStatus": "NOT_READY"
    }
  },
  "actionCapabilities": {
    "canEdit": false,
    "canConfirm": false,
    "canCancel": true,
    "canRegenerate": false,
    "canDownload": false
  }
}
```

### 29.3 统一错误

```json
{
  "error": {
    "code": "VERSION_CONFLICT",
    "message": "任务已变化，请刷新后继续",
    "correlationId": "corr-id",
    "retryable": false,
    "fieldErrors": [],
    "currentStateVersion": 18
  }
}
```

### 29.4 SSE

SSE 事件包含：

```text
eventId
taskId
phase
stateVersion
updatedAt
correlationId
```

客户端忽略旧 stateVersion；发现版本跳跃时重新获取任务详情。

---

## 三十、核心数据模型

### 30.1 `parent_task`

```text
id PK
user_id
client_task_id
phase
consistency_level
analysis_result_json
analysis_result_hash
user_requirement_raw
user_requirement_normalized
assigned_project_uuid
state_version
created_at
updated_at
```

约束：

```text
UNIQUE(user_id, client_task_id)
```

### 30.2 `asset`

```text
id PK
parent_task_id
source_type
role
order_no
required
version
sha256
object_key
thumbnail_key
used_for_analysis
used_for_generation
libtv_node_key
created_at
```

### 30.3 `canvas_project`

```text
id PK
user_id
project_uuid
mutation_state
execution_state
reserved_parent_count
prepared_video_count
reservation_opened_at
batch_opened_at
seal_deadline
state_version
created_at
updated_at
```

部分唯一索引：

```sql
CREATE UNIQUE INDEX uq_canvas_open_per_user
ON canvas_project(user_id)
WHERE mutation_state = 'OPEN';

CREATE UNIQUE INDEX uq_canvas_draining_per_user
ON canvas_project(user_id)
WHERE mutation_state = 'DRAINING';
```

### 30.4 `generation_variant`

```text
id PK
parent_task_id
variant_type
revision
prompt_text
prompt_hash
prompt_template_version
generation_config_json
generation_config_hash
ordered_storyboard_assets_hash
schema_snapshot_id
confirmed_at
created_at
```

### 30.5 `generation_attempt`

```text
id PK
variant_id
project_uuid
group_node_key
video_node_key
intent_hash
status
state_version
task_id
launch_started_at
process_started_at
runner_host_id
runner_execution_backend
runner_execution_ref
runner_process_id
runner_process_started_at
runner_process_nonce
runner_executable_hash
runner_command_hash
stdout_ref
stderr_ref
terminal_result_ref
exit_code
last_error_code
charge_status
billing_source
created_at
updated_at
```

关键约束：

```text
同一 project_uuid + video_node_key 最多一个活动 attempt
活动或成功 intent_hash 唯一
```

### 30.6 `generation_command`

```text
id PK
attempt_id UNIQUE
status
protocol_version
claim_owner
lease_expires_at
launch_started_at
process_started_at
created_at
updated_at
```

### 30.7 `materialization_operation`

```text
id PK
saga_id
step_type
expected_remote_identity
remote_node_key
status
attempt_count
stdout_ref
stderr_ref
started_at
completed_at
last_error_code
```

### 30.8 `points_reservation`

```text
id PK
user_id
business_date
attempt_id UNIQUE
estimated_points
actual_points
charge_status
billing_source
status
created_at
settled_at
```

### 30.9 `points_ledger`

```text
id PK
user_id
business_date
attempt_id
entry_type
points
reason
operator_id
created_at
```

`entry_type`：

```text
RESERVE / CONSUME / RELEASE / ADJUST / UNCERTAIN
```

### 30.10 `download_artifact`

```text
id PK
attempt_id
status
source_url_hash
object_key
sha256
size_bytes
duration_seconds
width
height
has_audio
source_type
revision
created_at
updated_at
```

### 30.11 `validation_result`

```text
id PK
attempt_id
status
coverage
rule_version
model_version
issue_codes_json
evidence_object_keys_json
summary
created_at
```

### 30.12 `api_idempotency_record`

```text
tenant_id
operation_type
idempotency_key
payload_hash
response_status
response_body_ref
created_at
expires_at
```

唯一约束：

```text
UNIQUE(tenant_id, operation_type, idempotency_key)
```

### 30.13 `audit_event`

```text
id PK
actor_id
action
entity_type
entity_id
from_state
to_state
reason
correlation_id
evidence_refs_json
created_at
```

### 30.14 `outbox_event`

```text
id PK
aggregate_type
aggregate_id
event_type
payload_json
status
attempt_count
next_attempt_at
created_at
published_at
```

业务状态和 Outbox 在同一 PostgreSQL 事务中写入。Worker 根据 Outbox 发布 SSE、通知和异步任务，重复发布由消费端幂等处理。

### 30.15 `model_schema_snapshot`

```text
id PK
cli_version
account_id
team_id
workspace_id
model_key
schema_json
compatibility_fingerprint
fetched_at
expires_at
```

### 30.16 `visual_fact_cache`

```text
cache_key PK
ordered_storyboard_hash
model_version
schema_version
facts_json
created_at
expires_at
```

### 30.17 `manual_fact_revision`

```text
id PK
parent_task_id
base_analysis_hash
revision
facts_json
operator_id
reason
created_at
```

### 30.18 `task_confirmation_version`

```text
id PK
parent_task_id
revision
analysis_result_hash
stable_prompt_hash
dynamic_prompt_hash
ordered_storyboard_assets_hash
generation_config_hash
schema_snapshot_id
confirmed_by
confirmed_at
```

### 30.19 `generation_reference_asset`

```text
id PK
generation_variant_id
asset_id
order_no
remote_node_key
created_at
```

唯一约束：

```text
UNIQUE(generation_variant_id, order_no)
UNIQUE(generation_variant_id, asset_id)
```

### 30.20 `materialization_saga`

```text
id PK
parent_task_id
project_uuid
status
state_version
created_at
updated_at
```

### 30.21 `runner_host`

```text
id PK
hostname
os_type
os_version
protocol_version
service_version
service_instance_id
status
last_heartbeat_at
free_disk_percent
created_at
updated_at
```

### 30.22 `runtime_config_version`

```text
id PK
version
config_json
changed_by
change_reason
created_at
rolled_back_from
```

### 30.23 `user_daily_points_summary`

```text
user_id
business_date
consumed_points
reserved_points
uncertain_points
state_version
updated_at
```

唯一约束：

```text
UNIQUE(user_id, business_date)
```

### 30.24 数据库锁顺序

跨表事务统一使用以下顺序：

```text
user_daily_points_summary
→ canvas_project
→ generation_attempt
→ generation_command
→ capacity_slot
→ points_reservation
```

默认使用 READ COMMITTED + 显式行锁 + 唯一约束 + CAS。积分竞争等需要更强隔离的局部事务可以使用 SERIALIZABLE，并设置有限重试。

### 30.25 容量槽实现

第一期可使用固定槽位表简化三级 lease：

```text
capacity_slot(
  scope_type,     -- GLOBAL / USER / PROJECT
  scope_id,
  slot_no,
  command_id,
  lease_expires_at,
  updated_at
)
UNIQUE(scope_type, scope_id, slot_no)
```

Dispatcher 按 `GLOBAL → USER → PROJECT` 顺序领取槽位。终态或管理员确认释放后清空 command_id。UNKNOWN 任务保留槽位或计入 uncertain exposure，避免系统将同一不确定容量再次分配。

---

## 三十一、运行配置基线

```yaml
app:
  timezone: Asia/Shanghai
  protocol_version: 1

pipeline_concurrency:
  local_preprocess: 20
  ai_analysis: 8
  materialization_global: 6
  materialization_per_project: 1
  generation_same_project: 4
  generation_per_user: 6
  generation_global: 12
  download: 8
  technical_validation: 6
  ai_validation: 2

prepared_queue:
  low_watermark: 12
  high_watermark: 24

canvas:
  parent_task_soft_limit: 5
  parent_task_hard_limit: 10
  video_node_soft_limit: 10
  remote_node_soft_limit: 50
  remote_node_hard_limit: 100
  grace_seconds_when_slots_idle: 5
  batch_window_seconds: 20
  open_max_minutes: 10
  draining_max_minutes: 10

model_registry:
  soft_ttl_minutes: 10
  hard_ttl_minutes: 30

points:
  daily_user_limit: 5000
  team_limit: null
  business_timezone: Asia/Shanghai
  prelaunch_stale_minutes: 120

runner:
  execution_backend: WINDOWS_COMMAND_HOST
  claim_lease_seconds: 60
  heartbeat_seconds: 15
  command_host_heartbeat_seconds: 15
  launch_confirmation_timeout_seconds: 30
  disk_warn_free_percent: 15
  disk_stop_free_percent: 5

prompt:
  target_max_chars: 1300
  extended_max_chars: 1600
  safety_soft_max_chars: 1850

validation:
  ai_sample_rate_steady: 0.10
  ai_sample_rate_calibration_mid: 0.20
  ai_full_review_first_videos: 200
  ai_p95_target_seconds: 60
  technical_duration_min_seconds: 9.0
  technical_duration_max_seconds: 11.0
  aspect_ratio_tolerance: 0.01

retention:
  input_delete_after_materialization: true
  output_days: 7
  logs_days: 90
  audit_days: 365
  remote_restore_enabled: true

object_storage:
  provider: minio
  data_root: "F:/libtv-agent/minio"
  zip_enabled: false

ai:
  provider: openai
  api: responses
  model: gpt-5.6-sol
  structured_output: true

auth:
  provider: builtin
  registration_enabled: false
  password_hash: argon2id
  session_store: server
```

所有运行配置：

- 版本化；
- 记录修改人、原因和时间；
- 支持回滚；
- 高风险配置由管理员权限控制；
- 并发配置修改后进入 15 分钟观察窗口；
- 全局生成并发提高时同步检查 PREPARED 水位；
- 数值不能突破实时 LibTV schema 和账号能力。

## 三十二、监控与告警

### 32.1 吞吐指标

```text
parent_tasks_created_total
videos_prepared_total
videos_submitted_total
videos_succeeded_total
videos_deliverable_total
videos_deliverable_per_hour
```

### 32.2 流水线指标

```text
queue_depth_preprocess
queue_depth_ai
queue_depth_materialization
queue_depth_prepared
queue_depth_generation
queue_depth_download
queue_depth_validation
```

### 32.3 延迟指标

```text
preprocess_duration_seconds
ai_analysis_duration_seconds
confirmation_wait_seconds
materialization_duration_seconds
prepared_wait_seconds
generation_duration_seconds
download_duration_seconds
validation_duration_seconds
end_to_end_duration_seconds
```

全部统计 p50、p95、p99。

### 32.4 稳定性指标

```text
duplicate_generation_total
cross_task_connection_total
unknown_after_submit_rate
cli_abnormal_exit_rate
materialization_uncertain_rate
schema_refresh_failure_rate
download_failure_rate
```

### 32.5 利用率

```text
generation_slot_utilization
prepared_starvation_seconds
runner_active_command_hosts
runner_orphan_processes
runner_recovery_commands
materialization_active_projects
```

### 32.6 Token 与积分

```text
ai_primary_calls_total
ai_repair_calls_total
ai_input_tokens_total
ai_output_tokens_total
storyboard_fact_cache_hit_rate
full_task_cache_hit_rate
points_reserved
points_consumed
points_uncertain
remote_restore_requested_total
remote_restore_succeeded_total
```

### 32.7 P0 告警

立即告警并冻结新付费提交：

- 出现重复 `node --run` 证据；
- 出现重复扣费证据；
- 出现跨用户或跨父任务素材连接；
- 个人积分预占被绕过；
- 付费核心数据库写入不可用；
- 同时存在 2 条 UNKNOWN，或 UNKNOWN 占用超过全局生成槽的 10%。

已有生成、查询、下载和对账继续运行。

---

## 三十三、安全、权限与审计

### 33.1 权限角色

```text
USER
TRUSTED_USER
OPERATOR
ADMIN
AUDITOR
```

- USER：创建、确认、查看和下载自己的任务；
- TRUSTED_USER：使用可信预设自动确认；
- OPERATOR：处理质量复核和普通异常；
- ADMIN：调整运行配置、隔离画布和处理 UNKNOWN；
- AUDITOR：只读查看账本与审计。

### 33.2 浏览器与 API

实现：

- 系统内置账号与管理员邀请制，不开放自主注册；
- 密码使用 Argon2id 哈希，认证状态使用服务端安全会话；
- 第一期不接企业微信、飞书或其他 SSO；
- 对象归属校验；
- CSRF 防护；
- Secure、HttpOnly、SameSite 会话；
- 严格 CSP；
- 输出编码；
- 敏感页面 `Cache-Control: no-store`；
- 签名下载 URL 短期有效；
- 埋点不保存原始提示词、凭据和签名 URL。

### 33.3 CLI 凭据

- 生产账号由 Secret Manager 或受控环境变量提供；
- Runner 环境中按最小权限加载；
- 日志统一脱敏；
- 账号切换由部署流程完成；
- CLI 版本升级先在 canary 环境验证。

### 33.4 审计动作

以下动作写入 audit_event：

- 确认和批量确认；
- 接受质量风险；
- 重新生成；
- 取消；
- UNKNOWN 分类；
- 积分调整；
- 画布隔离与释放；
- 并发配置修改；
- schema 强制刷新；
- 数据删除；
- 从 LibTV 远程项目找回。

### 33.5 数据保留、删除与远程找回

默认策略：

```text
原始输入素材：成功物化到 LibTV 后删除
生成视频：7 天
ZIP：不生成、不保存
CLI stdout/stderr：90 天
质量检查证据：90 天
API 幂等记录：至少 90 天
积分账本与审计：至少 365 天，按公司财务和审计要求延长
```

删除流程：

1. 到期对象进入待删除队列；
2. 数据库先标记 `deletion_pending_at`；
3. 对象存储删除成功后写 `deleted_at`；
4. 保留对象 Hash、积分、projectUuid、groupNodeKey、videoNodeKey、taskId 和审计摘要；
5. 活动任务、UNKNOWN、人工复核和争议任务暂停自动删除；
6. 用户界面展示准确的计划删除日期。

远程找回规则：

- 服务器生成视频到期删除后，用户可以从原 LibTV 远程项目重新下载仍存在的视频；
- 找回创建新的下载 artifact revision，不创建新的 generation attempt；
- 找回不消耗生成积分；
- 远程结果不存在或 URL 已永久失效时，返回明确状态；
- 重新生成始终需要用户单独发起并重新计费。

## 三十四、部署拓扑

### 34.1 受控 MVP

```text
1 × Windows 运行主机
1 × FastAPI API
1 × 通用 Worker
1 × Runner Windows Service
1 × PostgreSQL
1 × MinIO
0 × Redis（第一期核心路径）
```

API、Worker、PostgreSQL 和 MinIO 可以采用 Windows 原生服务或 Docker Desktop/兼容容器运行，Docker Desktop 内存限制建议约 6 GB，MinIO 数据卷落在 `F:` 盘。Runner Windows Service、command-host 和 `libtv.exe` 必须运行在 Windows 宿主机。

当前 Windows 11 Pro 电脑同时用于开发和 1–2 名用户的受控 MVP。系统稳定后，通过 SSH 部署到另一台长期在线的 Windows 电脑；代码继续在当前电脑编辑，通过构建产物和部署脚本发布，不要求在远程主机直接修改代码。真实 LibTV 生成、Windows 服务恢复和主机重启测试在 Windows 主机完成。

### 34.2 生产扩容

```text
2 × FastAPI API
2–4 × 通用 Worker
1–2 × Windows Runner 主机
托管 PostgreSQL 高可用
对象存储
Redis（SSE/缓存）
```

多 Runner 主机上线前需增加：

- host 级容量；
- commandHostId 和 serviceInstanceId 全局唯一；
- host 故障对账；
- 日志集中收集；
- Runner protocolVersion 兼容检查。

### 34.3 环境隔离

```text
DEV
STAGING
PRODUCTION
```

分别使用：

- 独立数据库；
- 独立对象存储前缀；
- 独立 LibTV project/workspace；
- 独立 Secret；
- 独立运行配置。

### 34.4 Windows 运行基线

```text
生产运行：Windows 10/11 或 Windows Server，64 位
CLI：官方 libtv.exe 1.1.1（升级需 canary）
Runner：Windows Service + command-host
媒体检查：Windows 版 ffmpeg / ffprobe
数据库：原生或托管 PostgreSQL；受控 MVP 可使用 Docker Desktop
文件系统：NTFS，本地日志与临时目录预留容量并监控
```

Windows Home/Pro/Server 的具体选择不影响业务合同，但必须支持 Windows Service、稳定网络、开机自启、磁盘监控和关闭睡眠。生产主机不得依赖用户保持桌面登录。

### 34.5 网络访问基线

- 局域网用户通过 Windows 主机的局域网地址访问 Web 系统；
- 偶尔远程访问的授权设备安装 Tailscale，并通过 Tailnet 私网地址访问；
- 不启用 Tailscale Funnel，不公开暴露服务；
- 不启用 Exit Node，普通互联网流量不经过本系统主机；
- PostgreSQL、MinIO、Runner 管理接口和 command-host 仅监听受控本机或私网接口，不得暴露到公网；
- 当前没有域名，第一期不以公网域名作为上线前置条件。

---

## 三十五、Fake / Replay LibTV Adapter

为加快开发和减少付费测试，代码必须提供：

```text
RealLibTVAdapter
FakeLibTVAdapter
ReplayLibTVAdapter
```

### 35.1 Fake Adapter 场景

可配置模拟：

- group 创建成功；
- 第 N 张图片上传失败；
- 参数写入后超时；
- 节点已创建但本地尚未保存 nodeKey；
- taskId 输出前进程退出；
- taskId 输出后进程退出；
- 生成成功；
- 生成终态失败；
- 限流；
- 下载中断；
- schema 改变；
- stdout/stderr 乱序；
- Runner Windows Service 重启但 command-host 仍在运行；
- command-host 创建成功但数据库写回失败；
- command-host PID 被系统复用但进程启动时间或 nonce 不匹配；
- Windows 主机重启导致本地进程消失但远程受理状态不明；
- terminal result 已写但 Runner 尚未写回数据库；
- 日志磁盘写满；
- 远程找回成功和远程结果已失效。

### 35.2 Replay Adapter

回放脱敏后的真实记录：

```text
命令参数
stdout 时间序列
stderr 时间序列
退出码
远程读取快照
```

CI 默认使用 Fake/Replay；真实平台测试只覆盖平台行为、并发、耗时和积分。

---

## 三十六、测试与验收

### 36.1 单元测试

覆盖：

- Hash 和 canonical JSON；
- 时间轴计算；
- required 分镜覆盖；
- A/B 差异；
- Prompt 字符压缩；
- modeType 选择；
- schema compatibility；
- 状态 CAS；
- 积分预占与结算；
- 文件命名；
- 错误码映射。

### 36.2 集成测试

使用 Fake/Replay 覆盖：

- 完整快速路径；
- 批量确认；
- 远程物化恢复；
- Worker/API 重启；
- Runner Windows Service 重启；
- command-host 存活时 Runner Windows Service 重启并恢复观察；
- Windows 主机整机重启；
- Windows Service Control Manager 自动拉起 Runner；
- PID 复用、nonce 冲突和孤儿 command-host；
- Runner 日志磁盘写满；
- 网络结果不明；
- UNKNOWN 对账；
- 下载重试；
- 服务器成品保留 7 天，到期后从远程结果找回；
- 部分成功交付；
- 并发抢占同一 node/intent；
- 积分日切；
- schema 兼容和不兼容变化。

### 36.3 受控 MVP 真实平台门槛

首轮开放 1–2 名用户：

```text
真实父任务：≥ 30 套
真实视频：≥ 60 条
同画布并发：4
全局并发：12
持续运行：≥ 4 小时
```

验收：

```text
重复正式生成：0
跨父任务连线：0
跨用户画布分配：0
素材顺序错误：0
积分预占绕过：0
视频解码成功率：100%
10 秒目标实际时长：9.0–11.0 秒
9:16 比例偏差：≤ 1%
UNKNOWN_AFTER_SUBMIT：< 1%
系统导致的限流：< 2%
有任务积压时生成槽利用率：≥ 80%
低风险任务自动完成率：≥ 80%
```

### 36.4 生产放量门槛

```text
真实视频：≥ 500 条
覆盖真实业务日：≥ 3 天
连续 soak：≥ 24 小时
峰值突发测试：≥ 2 小时
P0/P1 缺陷：0
重复正式生成：0
跨任务连接：0
UNKNOWN_AFTER_SUBMIT：< 0.5%
UNKNOWN 状态下自动重新提交：0
系统导致限流：< 1%
Fake/Replay 故障注入：≥ 10,000 次
相对前一级 p95 退化：≤ 20%
```

### 36.5 并发扩容门槛

每一级完成至少 100 条真实视频并稳定运行 60 分钟：

```text
同画布 4 → 6 → 8
全局 12 → 16 → 20
```

记录：

- 成功率；
- p50/p95/p99；
- 限流；
- UNKNOWN；
- CLI 异常；
- 单条积分；
- 画布查询延迟；
- 生成槽利用率。

### 36.6 用户验收

至少 5 名内部用户完成：

- 批量上传；
- 调整分镜顺序；
- 批量确认；
- 查看生成状态；
- 分别下载稳定版和动态版；
- 查看部分成功任务；
- 重新下载；
- 从 LibTV 远程项目找回；
- 提交重新生成。

关键任务完成率目标 100%，重新下载与重新生成在界面上明确区分。

---

## 三十七、灰度与上线阶段

### 第一阶段：开发与模拟器验证

目标：完成核心闭环。

- API、DDL 和状态机冻结；
- Fake/Replay Adapter 完成；
- 本地预处理、一次 AI 调用、提示词模板完成；
- 画布分配和 Saga 完成；
- generation command 与 Runner Supervisor 完成；
- 下载和本地检查完成；
- 核心故障注入通过。

### 第二阶段：受控 MVP

目标：验证真实 LibTV 行为和生产速度。

- 1–2 名用户；
- 同画布 4、全局 12；
- 自动确认只开放 PASS；
- 前 200 条真实视频执行全量轻量 AI 审查，之后按第二十八章逐步降低低风险抽样比例；
- 管理员工作时段值守；
- 每日复盘吞吐、卡点、UNKNOWN 和人工介入。

### 第三阶段：团队放量

目标：覆盖约 10 名用户和每天约 100 套父任务。

- 可信用户开启低风险 WARNING 自动确认；
- 优化 AI 和物化并发；
- 根据容量报告提升全局并发；
- 累计完成至少 500 条真实视频、覆盖 3 个业务日并完成 24 小时 soak；
- 固化 Runbook 和告警升级链路。

### 第四阶段：扩容与优化

- 同画布 6/8 验证；
- 全局 16/20 验证；
- 多 Runner 主机；
- 更高缓存命中；
- 自动并发建议；
- 投放数据接口和反馈字段。

---

## 三十八、发布、停止与恢复

### 38.1 发布前检查

- 数据库迁移完成；
- N 与 N-1 版本兼容当前 protocolVersion；
- Model Registry 有有效快照；
- LibTV 账号、teamId 和余额校验通过；
- Windows Runner 主机、Runner Service、磁盘和日志目录健康；
- 备份恢复演练完成；
- 回滚演练完成；
- P0/P1 缺陷清零；
- 值班人与业务停止授权人明确。

### 38.2 停止顺序

1. 开启全局暂停开关，停止领取新 generation command；
2. 暂停新的付费确认；
3. 已运行 CLI 继续收敛；
4. 查询、下载、质量检查和对账继续；
5. 状态证据不完整的 attempt 转 UNKNOWN；
6. 回滚应用；
7. 对账活动 command、points reservation 和远程节点；
8. 单用户、单并发 canary 恢复；
9. 逐步恢复默认并发。

### 38.3 灾难恢复

恢复后默认冻结新付费提交：

1. 确定恢复点和不确定时间窗；
2. 对照数据库、Runner Service、command-host、CLI 进程、terminal result、日志和 LibTV 远程节点；
3. 重建活动 command、积分和容量视图；
4. 不确定任务进入 UNCERTAIN/UNKNOWN；
5. 对账完成后由负责人批准恢复；
6. 先恢复下载与查询，再恢复新生成。

---

## 三十九、管理员与用户界面

### 39.1 普通用户页面

1. 生产工作台；
2. 新建批次；
3. 待确认；
4. 结果与下载；
5. 异常中心。

工作台建议列：

```text
任务
素材完整性
风险
稳定版状态
动态版状态
下载
质量
可交付
预计积分
今日剩余积分
更新时间
操作
```

### 39.2 管理员页面

- 生成容量；
- PREPARED 队列；
- 画布状态；
- UNKNOWN 对账；
- Model Registry；
- 积分预占与调整；
- Runner Service、command-host 与 CLI 进程；
- 错误和告警；
- 审计查询。

### 39.3 关键文案

重新下载：

> 重新获取服务器 7 天保留期内仍存在的已生成文件，不消耗生成积分。

远程找回：

> 服务器文件已到期时，从原 LibTV 远程项目重新获取结果；不消耗生成积分。

重新生成：

> 创建新视频版本，将产生新的生成积分消耗。

UNKNOWN：

> 平台接收状态正在核对。系统会先确认原任务结果，以保护本次积分和生成记录。

部分成功：

> 已通过的版本可以立即下载，其他版本正在处理或等待确认。

---

## 四十、实施任务拆分

### 40.1 后端

- [ ] PostgreSQL DDL 与迁移；
- [ ] 任务、素材、确认 API；
- [ ] Idempotency-Key 中间件；
- [ ] 状态 CAS 服务；
- [ ] 本地预处理；
- [ ] AI Adapter 与 JSON Schema；
- [ ] 缓存模块；
- [ ] Prompt 模板与时间轴脚本；
- [ ] Model Registry；
- [ ] 画布分配；
- [ ] Materialization Saga；
- [ ] generation command；
- [ ] Dispatcher；
- [ ] Runner Supervisor 集成；
- [ ] Reconciliation；
- [ ] 积分预占与账本；
- [ ] 下载、远程找回与对象存储；
- [ ] 技术质量检查；
- [ ] SSE；
- [ ] 管理后台 API；
- [ ] 审计与告警。

### 40.2 前端

- [ ] 批量上传；
- [ ] 分镜排序；
- [ ] 分析结果与风险展示；
- [ ] 单套和批量确认；
- [ ] 实时状态；
- [ ] 稳定版/动态版独立状态；
- [ ] 部分成功下载；
- [ ] 从 LibTV 远程项目找回；
- [ ] 积分额度展示；
- [ ] 异常中心；
- [ ] 管理员对账页面；
- [ ] 运行配置页面。

### 40.3 测试

- [ ] 单元测试；
- [ ] Fake Adapter；
- [ ] Replay fixtures；
- [ ] Saga 故障注入；
- [ ] 幂等并发测试；
- [ ] 积分竞争测试；
- [ ] Runner Service 重启、Windows 主机重启、command-host 恢复与磁盘阈值测试；
- [ ] UNKNOWN 对账测试；
- [ ] 下载中断与远程找回测试；
- [ ] 质量检查测试；
- [ ] 同画布 4 / 全局 12 压测；
- [ ] 用户验收；
- [ ] 回滚与恢复演练。

### 40.4 运维

- [ ] DEV/STAGING/PRODUCTION 环境；
- [ ] PostgreSQL 备份；
- [ ] 对象存储生命周期；
- [ ] Runner Windows Service 安装、升级、回滚和服务恢复配置；
- [ ] command-host 可执行程序、持久目录和 ACL；
- [ ] 日志采集和脱敏；
- [ ] Metrics 和 Dashboard；
- [ ] P0/P1 告警；
- [ ] Secret 管理；
- [ ] CLI canary 升级流程；
- [ ] 值班 Runbook。

---

## 四十一、交付物与签字门禁

进入受控 MVP 前必须实际交付：

1. `openapi.yaml`；
2. 数据库 DDL 和迁移脚本；
3. 机器可读状态机定义；
4. AI 输出 JSON Schema；
5. Prompt 模板和版本说明；
6. LibTV Adapter 命令合同；
7. Fake/Replay Adapter；
8. Runner Windows Service、command-host 与恢复配置；
9. 运行配置文件；
10. 单元与集成测试报告；
11. 真实平台受控测试报告；
12. 部署拓扑和环境清单；
13. 监控与告警清单；
14. Runbook；
15. 备份恢复和回滚演练记录；
16. UX 原型与用户验收记录。

签字角色：

- 架构负责人；
- 后端负责人；
- 前端负责人；
- 测试负责人；
- 运维负责人；
- 业务用户代表。

文档本身是实施基线；以上文件、代码、测试和演练记录完成后，才构成上线交付包。

---

## 四十二、最终运行原则

1. 系统是一台固定、快速、可批量运行的视频生产机器；
2. 大模型只处理视觉理解、语义判断和提示词内容；
3. 脚本负责所有固定动作、数值计算、校验、CLI 调用、等待和下载；
4. 正常任务优先一次主要多模态调用；
5. 五段流水线持续并行，生成槽有积压时保持高利用率；
6. 延迟物化减少无效远程节点和重复 CLI 操作；第一期不跨父任务复用 LibTV 图片节点；
7. PostgreSQL 保存所有正式付费命令和状态；
8. 同一生成意图保持一次正式提交；
9. UNKNOWN 先对账，积分和远程现场保持可追溯；
10. 下载、远程找回与质量检查独立运行，不占用新的生成能力；
11. 稳定版和动态版分别交付，部分成功可以先产生业务价值；
12. Token 优化服务于速度和稳定性，不增加额外生产等待；
13. 第一阶段保持模块化单体，按实际容量逐步扩展；
14. 所有配置、模板、状态和人工动作均版本化并可审计；
15. 每次优化以吞吐、端到端时延、稳定性和人工介入率验证效果。

---

# 附录 A：提示词渲染示例

## A.1 稳定版模板

```text
Use {{Node "IMG-..."}} as the complete ordered storyboard references for scene, model and garment identity.

Keep the same model, garment, colors, print, logo, text and scene identity throughout.
Preserve the garment's original fit, proportions and fabric structure.

Shot 1 (0.0–4.0s): [framing]. The model [action]. The camera [camera].
Present [productDisplay] clearly and naturally.

Shot 2 (4.0–7.0s): ...
Shot 3 (7.0–10.0s): ...

Use smooth transitions, natural body mechanics and stable product visibility.
Keep the background and lighting coherent across the complete video.
Use only the garment's original print, logo and text.

User direction: [normalized requirement].
Task correction: [optional concise correction].
```

## A.2 动态版模板

```text
Use {{Node "IMG-..."}} as the complete ordered storyboard references for scene, model and garment identity.

Keep the same model, garment, colors, print, logo, text and scene identity throughout.
Preserve the garment's original fit, proportions and fabric structure.

Shot 1 (0.0–2.0s): Create a strong product-led opening with [action/camera].
Shot 2 (2.0–5.0s): ...
Shot 3 (5.0–7.5s): ...
Shot 4 (7.5–10.0s): Finish with a clear product view and a natural settled pose.

Use energetic but controlled movement, coherent cuts and smooth camera tracking.
Keep the main selling point readable during the key display moments.
Maintain continuous lighting and background identity.
Use only the garment's original print, logo and text.

User direction: [normalized requirement].
Task correction: [optional concise correction].
```

---

# 附录 B：核心错误码

| 错误码 | 含义 | 自动动作 |
| --- | --- | --- |
| `INPUT_INVALID` | 输入文件或数量不符合要求 | 返回用户修改 |
| `ANALYSIS_SCHEMA_INVALID` | AI 结构化结果校验失败 | 执行一次定向修复 |
| `CONSISTENCY_REVIEW_REQUIRED` | 商品一致性需确认 | 进入待确认 |
| `SCHEMA_STALE` | 模型快照过期 | 单飞刷新 |
| `SCHEMA_INCOMPATIBLE` | 当前任务参数受影响 | 生成新确认版本 |
| `POINTS_LIMIT_EXCEEDED` | 个人额度不足 | 保持草稿或待确认 |
| `LIBTV_BALANCE_INSUFFICIENT` | 主账号积分不足 | 暂停新付费提交 |
| `MATERIALIZATION_RETRYABLE` | 远程准备临时失败 | 当前 operation 重试 |
| `MATERIALIZATION_UNCERTAIN` | 远程写结果不明确 | 隔离画布并对账 |
| `GENERATION_UNKNOWN` | 付费提交结果待核对 | 只读对账 |
| `GENERATION_TERMINAL_FAILED` | 平台明确失败 | 用户选择新版本 |
| `DOWNLOAD_RETRYABLE` | 下载临时失败 | 下载池重试 |
| `VALIDATION_MANUAL_REVIEW` | 成品需业务判断 | 进入人工质量复核 |
| `VERSION_CONFLICT` | 客户端版本落后 | 刷新任务详情 |
| `IDEMPOTENCY_KEY_REUSED` | 同 key 使用了不同请求 | 返回 409 |

---

# 附录 C：Runner 故障判定

| 证据 | 状态 | 处理 |
| --- | --- | --- |
| command 尚未领取 | READY | 正常领取 |
| CLAIMED 且 launchStartedAt 为空，lease 过期 | READY | 释放后重新领取同一 command |
| launchStartedAt 已写，command-host 创建结果不明 | UNKNOWN | 查询 Windows 进程、事件日志、terminal result、CLI 日志和 LibTV，不重新提交 |
| command-host 与 PID/启动时间/nonce 完整匹配 | RUNNING | 原 command-host 持续执行并恢复观察 |
| API/Worker 重启，command-host 存活 | RUNNING | 根据 runnerExecutionRef 恢复观察 |
| Runner Windows Service 重启，command-host 存活 | RUNNING | 校验进程身份后恢复观察，不创建替代进程 |
| PID 存在但启动时间、nonce、executableHash 或 commandHash 不匹配 | MANUAL_REVIEW | 视为身份冲突，禁止接管和重新提交 |
| terminal result 已存在且校验通过 | TERMINAL | 按终态 JSON 和退出码写回数据库 |
| Windows 主机重启 | RECOVERY | 冻结新提交并核对数据库、事件日志、terminal result、CLI 日志和远程状态 |
| 可用磁盘低于 15% | WARNING | 告警并清理非活动临时文件 |
| 可用磁盘低于 5% | PAUSED | 暂停创建新 command-host，已有任务继续收敛 |
| stdout/stderr 无法持久写入 | UNKNOWN | 不终止可能已提交的 command-host，执行远程对账 |
| 已捕获 taskId | RUNNING/UNKNOWN | 等待终态或对账 |
| CLI 非零退出，远程明确未受理 | FAILED_BEFORE_SUBMIT | chargeStatus=NOT_CHARGED 后可创建新 attempt |
| CLI 非零退出，远程受理情况不明 | UNKNOWN | 对账，不重新提交 |
| 远程存在有效视频 URL | SUCCEEDED | 进入下载 |
| 远程明确终态失败 | FAILED_TERMINAL | 根据 chargeStatus 结算，用户确认后新版本 |
| 本地与远程身份冲突 | MANUAL_REVIEW | 隔离画布 |

# 附录 D：受控 MVP 上线清单

```text
[ ] openapi.yaml 已冻结
[ ] DDL 与迁移已完成
[ ] 状态机定义已进入代码生成或契约测试
[ ] AI JSON Schema 已冻结
[ ] Prompt 模板已版本化
[ ] Fake/Replay Adapter 已进入 CI
[ ] Runner Windows Service 安装、开机自启、失败恢复和升级回滚已验证
[ ] command-host 前台运行 libtv.exe、服务重启恢复和进程身份校验已验证
[ ] Windows 主机重启、磁盘阈值和睡眠关闭已验证
[ ] 同画布 4 并发测试通过
[ ] 全局 12 并发测试通过
[ ] 重复正式提交为 0
[ ] 跨父任务 LibTV 图片节点复用已关闭
[ ] 跨任务素材连接为 0
[ ] 个人 5000 积分额度竞争测试通过
[ ] UNKNOWN 对账流程通过
[ ] 9–11 秒时长合同通过
[ ] 下载、远程找回与质量检查通过
[ ] P0/P1 缺陷为 0
[ ] 监控与告警上线
[ ] 回滚演练完成
[ ] 备份恢复演练完成
[ ] 业务用户验收完成
[ ] 值班与人工处理负责人明确
```
