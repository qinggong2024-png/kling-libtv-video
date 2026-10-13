# Director Studio V2 Real Sample Validation Report

日期：2026-10-13

范围：只读验证 Director Studio V2 MVP 的 Product Brief → Creative Direction → Production Package 闭环。

本轮没有修改代码、UI、Agent、workflow、Provider、Prompt 生成逻辑或数据结构。

## 结论

本轮验证为 **BLOCKED / Intake 部分通过**。

5 个真实素材都可以通过 Product Brief 的上传入口，品牌归属也可以保持为“通用风格”。但是点击“生成创意方向”后，所有样本都被同一个运行门阻断：

```text
OFFLINE_WORKFLOW_DISABLED
离线工作流当前不可用。由管理员核查，不切换到真实 Provider。
```

因此本轮没有任何样本产生可审查的 Direction A/B/C，也没有进入方向选择或 Production Package。不能据此评价方向差异、选择帮助或 Prompt 可执行性。

## Runtime Evidence

| 项目 | 结果 |
| --- | --- |
| 前端 | `http://127.0.0.1:5175/?view=images&pane=director` |
| 后端 live | `http://127.0.0.1:8000/api/v1/health/live` → HTTP 200 |
| 后端 ready | `http://127.0.0.1:8000/api/v1/health/ready` → HTTP 200 |
| 页面模式 | `离线 Fake 模式 · 不可交付` |
| 方向生成 | 被 `OFFLINE_WORKFLOW_DISABLED` 阻断 |
| Provider | 未调用 |
| 付费动作 | 未发生 |
| 生产数据写入 | 未发生 |

后端 readiness 通过并不代表 Director workflow 已启用。当前前端运行状态仍明确关闭方向生成工作流。

## Sample Matrix

### S1：暗黑风复杂印花

| 项目 | 记录 |
| --- | --- |
| 输入文件 | `var/artifacts/development/users/8a2fa57e-501a-4c74-885b-2274e13b29bd/inputs/0055d526-b56d-4d35-b5b9-649feaea6f33/normalized.jpg` |
| SHA-256 | `9A0D0032016C8EA426B1F25E8438C8FA3E990D6B2D905B5FBC746EBEC59108B5` |
| 可见商品事实 | 黑色长款连衣裙，深色底，密集金色/花卉类图案，穿着镜自拍 |
| 有效输入 | 商品图片；品牌归属为通用风格 |
| 未生效输入 | 目标受众、创作策略、视频类型等高级设置没有作为分析参数提交 |
| 上传 | 通过 |
| A/B/C | 未生成 |
| 选择原因 | 不适用 |
| Production Package | 未生成 |
| 人工修改点 | 没有进入可修改的方向或生产包 |
| 未满足需求 | 需要清晰商品正面图；当前图片是穿着自拍，商品边界和细节受人物、镜面和环境影响 |

### S2：泛读书成熟女性定位

| 项目 | 记录 |
| --- | --- |
| 输入文件 | `var/artifacts/development/users/27cf30ac-802f-47d4-aa5b-020e312395c0/inputs/00fbbdd4-340d-4078-a16a-d90eafc4bcd9/normalized.jpg` |
| SHA-256 | `14913FBAAA1095E8652E29F210886F16C0B266AB1322B7A2DCEDA504BFCAE7DD` |
| 可见商品事实 | 白底红色图案 T 恤，人物位于书店/书墙环境，女性穿着展示 |
| 有效输入 | 商品图片；品牌归属为通用风格 |
| 未生效输入 | “成熟女性”“读书人群”只是本次样本假设，当前页面没有把它们作为已生效分析字段 |
| 上传 | 通过 |
| A/B/C | 未生成 |
| 选择原因 | 不适用 |
| Production Package | 未生成 |
| 人工修改点 | 没有进入可修改的方向或生产包 |
| 未满足需求 | 当前素材是生活方式图，不是清晰商品正面图；受众定位无法作为有效 Brief 输入验证 |

### S3：极客男性定位

| 项目 | 记录 |
| --- | --- |
| 输入文件 | `var/artifacts/development/users/00000000-0000-0000-0000-000000000001/inputs/f0f99dd5-d8de-4bc5-be7f-51753e8b1718/normalized.jpg` |
| SHA-256 | `D596FA6949784323AAAA2DFB259E0BBEC6D689718A30172E948B67F9CBDAEBCC` |
| 可见商品事实 | 深色男性 T 恤，人物坐在桌游/娱乐环境中，商品部分被姿势和桌面遮挡 |
| 有效输入 | 商品图片；品牌归属为通用风格 |
| 未生效输入 | “极客男性”只是本次样本假设，当前没有作为有效受众字段提交 |
| 上传 | 通过 |
| A/B/C | 未生成 |
| 选择原因 | 不适用 |
| Production Package | 未生成 |
| 人工修改点 | 没有进入可修改的方向或生产包 |
| 未满足需求 | 需要单独商品正面图；当前生活方式图不足以锁定完整版型、图案和商品边界 |

### S4：普通基础款

| 项目 | 记录 |
| --- | --- |
| 输入文件 | `var/artifacts/development/users/00000000-0000-0000-0000-000000000001/inputs/932962e9-7490-41e3-a050-739618444bef/normalized.jpg` |
| SHA-256 | `C38A1C9B59B131B893C621562ABCB6DFEC3B055DE6664ECD2090FC88E31B0FB5` |
| 可见商品事实 | 黑色短袖 T 恤，正面平铺，白色文字“I HAD POTENTIAL” |
| 有效输入 | 商品图片；品牌归属为通用风格 |
| 未生效输入 | 受众、渠道、目标和高级创作偏好没有进入分析 |
| 上传 | 通过 |
| A/B/C | 未生成 |
| 选择原因 | 不适用 |
| Production Package | 未生成 |
| 人工修改点 | 没有进入可修改的方向或生产包 |
| 未满足需求 | 这是 5 个样本中最接近 Canonical Product 正面图的素材，但仍无法验证方向和 Prompt |

### S5：高复杂图案款

| 项目 | 记录 |
| --- | --- |
| 输入文件 | `var/artifacts/development/users/7bbefff3-e514-44db-91cd-083fd3764928/inputs/008a117e-2a68-4bbc-8be1-41d109b5feb0/normalized.jpg` |
| SHA-256 | `34141DFA08A75A2E1D27E84395F8FDB3B2114EBD4CF65AB96FD76F16A5E6B153` |
| 可见商品事实 | 白色背心，绿色滚边，正面包含国家公园主题插画和文字，人物穿着在户外环境中 |
| 有效输入 | 商品图片；品牌归属为通用风格 |
| 未生效输入 | “高复杂图案”是样本分类，未作为额外分析约束提交 |
| 上传 | 通过 |
| A/B/C | 未生成 |
| 选择原因 | 不适用 |
| Production Package | 未生成 |
| 人工修改点 | 没有进入可修改的方向或生产包 |
| 未满足需求 | 当前是穿着环境图；复杂图案的文字、边缘和完整轮廓需要单独正面商品图确认 |

## Required Output Assessment

| 目标 | 结果 | 判断 |
| --- | --- | --- |
| 方向 A/B/C 是否有差异 | 未验证 | 统一运行门阻断 |
| 方向是否帮助创意决策 | 未验证 | 没有方向卡可比较 |
| Prompt 是否可执行 | 未验证 | 没有生成图片或视频 Prompt |
| Production Package 完整性 | 未验证 | 没有进入第三阶段 |
| 商品事实是否能被稳定锁定 | 部分验证 | 只有 S4 接近合格商品正面输入 |
| 目标受众是否能影响结果 | 未验证 | 受众字段当前不是已生效输入 |

## 主要发现

### P0：运行模式阻断完整 MVP 闭环

页面允许上传真实素材，但生成方向时统一返回 `OFFLINE_WORKFLOW_DISABLED`。当前真实样本验证不能继续到 Creative Direction 或 Production Package。

需要由管理员/运行负责人核对实际 workflow 开关、运行 profile 和 Fake/real sample 边界。不能通过前端 readiness 200 推断 Director workflow 已可执行。

### P1：样本素材与 Canonical Product 要求不一致

S1、S2、S3、S5 都是人物穿着或生活方式照片。它们可以用于观察广告语境，但不能单独作为稳定的商品事实来源。真实样本重跑前，每个 SKU 至少需要一张清晰商品正面图，并记录商品事实、禁止变化项和 SHA-256。

S4 最适合先作为第一条真实闭环样本，因为它已经接近平铺正面图，商品边界、颜色和文字更容易核验。

### P1：受众定位目前没有进入有效 Brief

“泛读书成熟女性”“极客男性”等测试分类没有对应的已生效受众字段。高级创作设置目前显示为“计划支持”，不能把它们当作已经影响方向生成的输入。

因此后续必须区分：

- 商品本身能被图片观察到的事实；
- 本轮测试人员的受众假设；
- 已真正提交到 Director workflow 的字段。

## 下一步

1. 先关闭当前 `OFFLINE_WORKFLOW_DISABLED` 阻断，重新确认真实样本执行边界和是否仍然禁止 Provider。
2. 优先用 S4 的清晰正面商品图跑一次只读/不付费方向生成，先验证 A/B/C 和 Production Package。
3. 为 S1、S2、S3、S5 补充同一 SKU 的商品正面图，再重跑这 4 个样本。
4. 在 workflow 可用后，按同一记录模板补齐方向差异、选择原因、Prompt 可执行性、Package 完整性和人工修改点。
5. 在任何 Provider 或付费动作前，继续遵守 `REAL_SAMPLE_TEST_PROTOCOL_20261013.md` 与 `CRB5_SINGLE_SAMPLE_READINESS_20261013.md` 的单样本授权门。

## Evidence

- 本地页面：`http://127.0.0.1:5175/?view=images&pane=director`
- 本地 backend live/ready 均为 HTTP 200。
- 5 次上传均在 Product Brief 显示商品预览和“已就绪”。
- 5 次点击“生成创意方向”均未产生方向候选或 Production Package。
- 当前页面明确显示 `离线 Fake 模式 · 不可交付`。
- 当前没有 Provider 调用、真实媒体生成、付费提交或代码修改。
