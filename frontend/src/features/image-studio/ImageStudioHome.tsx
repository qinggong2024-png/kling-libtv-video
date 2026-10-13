import { ArrowRight, History, ImagePlus, Layers3, Sparkles, Type } from 'lucide-react'
import type { ImageStudioView } from './imageStudioNavigation'

export function ImageStudioHome({ taskCount, onOpen }: {
  taskCount: number
  onOpen: (view: ImageStudioView) => void
}) {
  return <section className="image-studio-home" aria-labelledby="image-studio-home-title">
    <header className="image-studio-home__header">
      <div>
        <span className="image-studio-home__eyebrow">IMAGE STUDIO</span>
        <h1 id="image-studio-home-title">图片工作室</h1>
        <p>从商品图和创意开始，快速产出服装广告素材。</p>
      </div>
    </header>

    <div className="image-studio-home__entries" aria-label="图片创作入口">
      <button type="button" className="image-studio-entry image-studio-entry--featured" onClick={() => onOpen('image-to-image')}>
        <span className="image-studio-entry__icon"><ImagePlus size={24} /></span>
        <span className="image-studio-entry__copy">
          <small>首选工作流</small>
          <strong>图生图</strong>
          <span>上传商品图和人物参考，生成可直接用于广告的画面。</span>
        </span>
        <ArrowRight className="image-studio-entry__arrow" size={20} />
      </button>

      <button type="button" className="image-studio-entry" onClick={() => onOpen('text-to-image')}>
        <span className="image-studio-entry__icon"><Type size={22} /></span>
        <span className="image-studio-entry__copy">
          <small>创意探索</small>
          <strong>文生图</strong>
          <span>从一句创意描述开始，探索风格、场景和构图方向。</span>
        </span>
        <ArrowRight className="image-studio-entry__arrow" size={20} />
      </button>

      <button type="button" className="image-studio-entry" onClick={() => onOpen('batch')}>
        <span className="image-studio-entry__icon"><Layers3 size={22} /></span>
        <span className="image-studio-entry__copy">
          <small>专业生产</small>
          <strong>批量生产</strong>
          <span>管理多套产品、素材编排、分镜和生成参数。</span>
        </span>
        <ArrowRight className="image-studio-entry__arrow" size={20} />
      </button>
    </div>

    <div className="image-studio-home__secondary">
      <button type="button" className="image-studio-history-link" onClick={() => onOpen('records')}>
        <span className="image-studio-history-link__icon"><History size={17} /></span>
        <span><strong>生图记录</strong><small>{taskCount ? `${taskCount} 个批次，查看进度和结果` : '查看已提交的任务和结果'}</small></span>
        <ArrowRight size={17} />
      </button>
      <div className="image-studio-home__note"><Sparkles size={16} /><span>先选择创作方式，复杂配置会在需要时出现。</span></div>
    </div>
  </section>
}
