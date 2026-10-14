import { Images, Layers3, Package, Save } from 'lucide-react'
import type { ReactNode } from 'react'
import type { ImageStudioView } from './imageStudioNavigation'

const modes = [
  { view: 'batch-create', label: '批量创作', Icon: Layers3 },
  { view: 'batch-products', label: '产品套装', Icon: Package },
  { view: 'batch-storyboard', label: '分镜生产', Icon: Images },
] as const

export function BatchStudio({ children, view, onOpen, saveState }: {
  children: ReactNode
  view: ImageStudioView
  onOpen: (view: ImageStudioView) => void
  saveState: 'saved' | 'saving' | 'error'
}) {
  const title = modes.find(mode => mode.view === view)?.label
  return <section className="image-batch-studio image-studio-batch" aria-labelledby="image-batch-title">
    <header className="image-batch-studio__header">
      <div>
        <h2 id="image-batch-title">{title}</h2>
      </div>
      <div className="image-batch-studio__actions">
        <span className={`image-center-save-state is-${saveState}`}><Save size={14} />{saveState === 'saved' ? '草稿已保存' : saveState === 'saving' ? '正在保存' : '草稿保存失败'}</span>
      </div>
    </header>
    <nav className="image-batch-modes" aria-label="批量生产">
      {modes.map(({ view: mode, label, Icon }) => <button type="button" key={mode}
        aria-current={view === mode ? 'page' : undefined} onClick={() => onOpen(mode)}>
        <Icon size={15} aria-hidden="true" />{label}
      </button>)}
    </nav>
    {children}
  </section>
}
