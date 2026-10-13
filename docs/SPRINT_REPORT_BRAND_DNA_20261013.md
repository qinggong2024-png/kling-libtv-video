# Sprint Report：Creative Core / Sprint 2 Brand DNA

日期：2026-10-13
状态：testing 与实际 main 工程验收通过，源码同步完成；未部署。

## 完成

- 复用 site-style-profiles / CatalogEditor 的已有配置读写，不新建品牌表。
- 新增 brand-dna.v1 只读投影：受众、视觉、人物表达、场景、镜头、禁用项、
  商品限制、目录 ID/版本、原目录快照和内容 hash。
- 在现有任务创建表单增加可选 brand_profile_id / brand_profile_version；
  新任务固化目录快照，PlanRevision 增加可选 brand_dna，旧存储无需迁移。
- 幂等指纹包含明确的品牌选择；无品牌请求保持原指纹格式。
- 先重放已创建任务，再读取最新目录；旧任务不会因目录更新而变成新任务。
- 品牌场景建议可用于三个 Fake 方向；受众和人物风格进入 Package 的建议字段。
- 旧包仅使用原冻结 plan；不读取当前目录来覆盖旧包。
- 前端按稳定 ID 选择品牌，同名目录不再误绑定；显示版本与绑定状态。

## 修改

- 新增 creative/brand_dna.py、专项纯测试及任务绑定 API 测试。
- 修改现有 creative workflow 的可选输入、快照与分析接线。
- 修改 Package 只读投影，保留完整 Brand DNA 来源；身份保持未提供。
- 新增独立前端品牌预览和选择适配器；在原导演页作小范围接线，保留已有布局。
- 无 ORM、迁移、State 扩展、Provider、支付、账本、自动学习或生产配置变更。

## 测试

- testing：后端组合 156 项通过；Ruff 通过。
- testing：前端 54 文件 / 331 项通过，lint、TypeScript 和外部 build 通过。
- 品牌配置读写、旧包不漂移、版本冲突、draft/retired 拒绝、幂等重放、
  hash 篡改、通用模式兼容通过。
- 浏览器：1440/1024/768/390 宽度 Package 复制、下载、刷新及失败恢复通过；
  1440/390 宽度同名品牌 ID/版本提交、三方向、选 B 后读取冻结受众通过。
- 测试均为隔离 SQLite / 合成 fixture；零 Provider、付费生成和生产写入。
- 实际 main：后端同组 156 项通过，Ruff 通过；
  前端 55 文件 / 327 项通过，lint、TypeScript 和外部 build 通过。
- 实际 main：同一四宽度 Package 与双宽度品牌流程独立通过。
- 两侧保留既有差异；只局部同步本轮源文件与文档，不同步 runtime、构建或截图。

## 发现问题

- 目录内 sourceUrls / evidenceLevel 是原配置记录，本轮未访问外站核验来源。
- 当前 Director analyze 仍为 Fake；品牌建议不等于产品事实或真实视觉理解。
- 人物风格只描述表达倾向，不锁定具体身份、脸或外貌。
- 本轮允许可选输入和快照合同增量，不执行 CreativeTask 全量迁移。
- 运行时真实品牌配置、真实 Provider 与正式站点易用性验收仍未执行。

## 下一步

- Sprint 3 增加独立人工评价，保留图片 PASS/REWORK/FAIL 和视频 PASS/FAIL。
- 评价数据追加保存，保持 QUALIFIED/APPROVED、计费与交付状态独立。
- 如现有持久化设施无法提供正确的幂等与历史留存，停止相应实施并提交具体差异。
