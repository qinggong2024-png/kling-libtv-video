import { ArrowLeft, ArrowRight, ImagePlus, Sparkles, Type } from 'lucide-react'

export function TextToImageStudio({ onBack, onOpenBatch }: {
  onBack: () => void
  onOpenBatch: () => void
}) {
  return <section className="image-quick-studio" aria-labelledby="text-to-image-title">
    <button type="button" className="image-studio-back" onClick={onBack}><ArrowLeft size={16} />图片工作室</button>
    <header className="image-quick-studio__header">
      <div><span className="image-studio-home__eyebrow">创意探索</span><h1 id="text-to-image-title">文生图</h1><p>把一句创意描述变成可继续打磨的服装广告方向。</p></div>
      <span className="image-quick-studio__badge"><Type size={15} />创意入口</span>
    </header>
    <div className="image-text-brief">
      <label htmlFor="image-text-brief-input">你想先探索什么？</label>
      <textarea id="image-text-brief-input" rows={5} placeholder="例如：夏日街头，年轻人穿着新款球衣，午后阳光，真实 UGC 广告感" />
      <div className="image-text-brief__suggestions" aria-label="创意方向">
        <span><Sparkles size={14} />真实 UGC</span>
        <span><Sparkles size={14} />商业摄影</span>
        <span><Sparkles size={14} />生活方式</span>
      </div>
    </div>
    <div className="image-quick-studio__action">
      <div><strong>先建立创意，再决定细节</strong><span>比例、模型和批量参数会在生成配置中按需展开。</span></div>
      <button type="button" className="primary-button" onClick={onOpenBatch}><ImagePlus size={17} />继续到生成配置<ArrowRight size={16} /></button>
    </div>
  </section>
}
