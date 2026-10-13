import { ArrowLeft, Layers3, Save } from 'lucide-react'
import type { ReactNode } from 'react'

export function BatchStudio({ children, onBack, saveState }: { children: ReactNode; onBack: () => void; saveState: 'saved' | 'saving' | 'error' }) {
  return <section className="image-batch-studio" aria-labelledby="image-batch-title">
    <header className="image-batch-studio__header">
      <div>
        <button type="button" className="image-studio-back" onClick={onBack}><ArrowLeft size={16} />图片工作室</button>
        <span className="image-studio-home__eyebrow">专业生产</span>
        <h1 id="image-batch-title">批量生产</h1>
        <p>集中管理套装、参考素材、生成模式和分镜任务。</p>
      </div>
      <div className="image-batch-studio__actions">
        <span className={`image-center-save-state is-${saveState}`}><Save size={14} />{saveState === 'saved' ? '草稿已保存' : saveState === 'saving' ? '正在保存' : '草稿保存失败'}</span>
        <span className="image-batch-studio__badge"><Layers3 size={16} />高级生产入口</span>
      </div>
    </header>
    {children}
  </section>
}
