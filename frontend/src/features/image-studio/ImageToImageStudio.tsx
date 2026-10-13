import { ArrowLeft, ArrowRight, ImagePlus, Layers3, Sparkles, UploadCloud } from 'lucide-react'

export function ImageToImageStudio({ onBack, onOpenBatch }: {
  onBack: () => void
  onOpenBatch: () => void
}) {
  return <section className="image-quick-studio" aria-labelledby="image-to-image-title">
    <button type="button" className="image-studio-back" onClick={onBack}><ArrowLeft size={16} />图片工作室</button>
    <header className="image-quick-studio__header">
      <div><span className="image-studio-home__eyebrow">快速创作</span><h1 id="image-to-image-title">图生图</h1><p>从商品图和人物参考开始，快速得到第一版广告画面。</p></div>
      <span className="image-quick-studio__badge"><Sparkles size={15} />核心工作流</span>
    </header>
    <div className="image-quick-studio__steps">
      <article><span><UploadCloud size={20} /></span><div><strong>上传参考素材</strong><p>商品图、人物图或场景图，先放入生产配置。</p></div></article>
      <ArrowRight className="image-quick-studio__step-arrow" size={18} />
      <article><span><ImagePlus size={20} /></span><div><strong>选择生成目标</strong><p>换装、场景迁移或广告素材，都可以继续调整。</p></div></article>
      <ArrowRight className="image-quick-studio__step-arrow" size={18} />
      <article><span><Layers3 size={20} /></span><div><strong>生成并审核</strong><p>提交后在生图记录中查看结果和审核状态。</p></div></article>
    </div>
    <div className="image-quick-studio__action">
      <div><strong>开始准备第一张广告图</strong><span>现有生成、审核和视频交接流程会在下一步继续使用。</span></div>
      <button type="button" className="primary-button" onClick={onOpenBatch}><ImagePlus size={17} />进入生成配置</button>
    </div>
  </section>
}
