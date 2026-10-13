import { ArrowLeft, History } from 'lucide-react'
import type { ReactNode } from 'react'

export function ImageRecords({ children, onBack }: { children: ReactNode; onBack: () => void }) {
  return <section className="image-records-studio" aria-labelledby="image-records-title">
    <header className="image-records-studio__header">
      <div>
        <button type="button" className="image-studio-back" onClick={onBack}><ArrowLeft size={16} />图片工作室</button>
        <span className="image-studio-home__eyebrow">历史与结果</span>
        <h1 id="image-records-title">生图记录</h1>
        <p>查看进度、审核结果，并把合格画面送入视频生产。</p>
      </div>
      <span className="image-records-studio__badge"><History size={16} />任务结果</span>
    </header>
    {children}
  </section>
}
