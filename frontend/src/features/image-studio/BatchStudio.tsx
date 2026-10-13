import { ArrowLeft, ArrowRight, Images, Layers3, Package, Save } from 'lucide-react'
import type { ReactNode } from 'react'
import type { ImageStudioView } from './imageStudioNavigation'

const titles = { 'batch-create': '批量创作', 'batch-products': '产品套装', 'batch-storyboard': '分镜生产' }

export function BatchStudio({ children, view, onOpen, onBack, saveState }: {
  children: ReactNode
  view: ImageStudioView
  onOpen: (view: ImageStudioView) => void
  onBack: () => void
  saveState: 'saved' | 'saving' | 'error'
}) {
  const title = view === 'batch' ? '批量生产' : titles[view as keyof typeof titles]
  return <section className="image-batch-studio" aria-labelledby="image-batch-title">
    <header className="image-batch-studio__header">
      <div>
        <button type="button" className="image-studio-back" onClick={onBack}><ArrowLeft size={16} />{view === 'batch' ? '图片工作室' : '批量生产'}</button>
        <span className="image-studio-home__eyebrow">专业生产</span>
        <h1 id="image-batch-title">{title}</h1>
      </div>
      <div className="image-batch-studio__actions">
        <span className={`image-center-save-state is-${saveState}`}><Save size={14} />{saveState === 'saved' ? '草稿已保存' : saveState === 'saving' ? '正在保存' : '草稿保存失败'}</span>
      </div>
    </header>
    {view === 'batch' ? <div className="image-batch-destinations">
      <button type="button" onClick={() => onOpen('batch-create')}><Layers3 size={22} /><span><strong>批量创作</strong><small>多套商品统一生成</small></span><ArrowRight size={18} /></button>
      <button type="button" onClick={() => onOpen('batch-products')}><Package size={22} /><span><strong>产品套装</strong><small>管理本批次商品和参考图</small></span><ArrowRight size={18} /></button>
      <button type="button" onClick={() => onOpen('batch-storyboard')}><Images size={22} /><span><strong>分镜生产</strong><small>有序镜头批量生成</small></span><ArrowRight size={18} /></button>
    </div> : <>{children}{view === 'batch-products' ? <button type="button" className="primary-button" onClick={() => onOpen('batch-create')}><ArrowRight size={16} />进入批量创作</button> : null}</>}
  </section>
}
