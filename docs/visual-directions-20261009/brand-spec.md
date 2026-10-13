# 衣影工坊视觉方向探索

日期：2026-10-09。状态：未选定，不替换冻结中的生产设计系统。

## 已知上下文

- 品牌名称来自现有产品规范；没有新提供的正式 Logo、VI 或字体文件。
- 本稿使用文字品牌和 Lucide Layers 图标作为临时工作区标识，不声称它是正式 Logo。
- 受众：跨境服装广告素材生产、审核和交付人员。
- 保留素材准备与生成配置两区、两区后的提交、同区素材排序与检查。
- 四个产品工作区及管理/设置入口保持原有语义。样稿只实现视频工作区。

## 三个方向

| 方向 | 色彩 | 字体候选 | 空间与交互 |
| --- | --- | --- | --- |
| A 明亮精密 | 冷白底、石墨文字、深青绿主动作 | Segoe UI Variable / Segoe UI + Microsoft YaHei | 左侧导航，平衡双栏，低噪声表单 |
| B 深色剪辑台 | 中性石墨底、灰白文字、黄绿主动作 | Bahnschrift + DengXian / Microsoft YaHei | 窄侧栏，素材区加宽，工具式小圆角 |
| C 素材工作台 | 白色内容、炭黑顶栏、莓红主动作 | Microsoft YaHei + Segoe UI | 水平导航，素材区优先，紧凑方形缩略图 |

字体为本机候选栈，未下载新字体。实际可用性与最终字体授权待方向选定后核实。
不要把本稿的主观方向描述当作用户效率实测结果。

## 素材与来源

- `media/look-01.jpg`：https://images.unsplash.com/photo-1539109136881-3be0616acf4b
- `media/look-02.jpg`：https://images.unsplash.com/photo-1483985988355-763728e1935b
- 图片只作穿搭参考样稿，不代表同一商品、用户私有资产或 AI 生成结果。
- `icons.js` 为本机 lucide-react 1.27.0 的 SVG 输出，ISC 许可，见 `LUCIDE-LICENSE.txt`。
- 图片生成工具本轮未返回可用文件；未改用付费 CLI 或调用生产 Provider。

## 边界与下一步

- 三个 HTML 可直接打开，无服务端、API 请求、真实任务、审核写入或扣费。
- 生成结果、配方和审核仅为明确标注的交互样稿。
- 当前不写 `direction-approved.md`；只有收到用户明确选择后记录批准来源。
- 选定方向后再修订正式 Design System，并开展 Video Studio 实际实现及 Checkpoint 1。
