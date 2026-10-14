import { History, ImagePlus, Layers3, Type } from 'lucide-react'
import { useRef } from 'react'
import type { ImageStudioView } from './imageStudioNavigation'

const modes = [
  { view: 'image-to-image', label: '图生图', Icon: ImagePlus },
  { view: 'text-to-image', label: '文生图', Icon: Type },
  { view: 'batch-create', label: '批量生产', Icon: Layers3 },
] as const

export function ImageStudioHeader({ view, taskCount, onOpen }: {
  view: ImageStudioView
  taskCount: number
  onOpen: (view: ImageStudioView) => void
}) {
  const buttons = useRef<Array<HTMLButtonElement | null>>([])
  const selected = view.startsWith('batch-') ? 'batch-create' : view
  return <header className="image-studio-header">
    <div className="image-studio-header__title">
      <h1>图片工作室</h1>
      <button type="button" className="image-studio-records-link" aria-current={view === 'records' ? 'page' : undefined}
        onClick={() => onOpen('records')} title="生图记录">
        <History size={16} /><span>生图记录</span>{taskCount ? <small>{taskCount}</small> : null}
      </button>
    </div>
    <div className="image-studio-modes" role="tablist" aria-label="图片创作模式">
      {modes.map(({ view: mode, label, Icon }, index) => <button key={mode} type="button" role="tab"
        id={`image-mode-${mode}`} aria-controls="image-studio-panel" aria-selected={selected === mode}
        tabIndex={selected === mode || (view === 'records' && index === 0) ? 0 : -1}
        ref={element => { buttons.current[index] = element }}
        onClick={() => onOpen(mode)}
        onKeyDown={event => {
          const next = event.key === 'ArrowRight' ? (index + 1) % modes.length
            : event.key === 'ArrowLeft' ? (index + modes.length - 1) % modes.length
              : event.key === 'Home' ? 0 : event.key === 'End' ? modes.length - 1 : null
          if (next === null) return
          event.preventDefault()
          onOpen(modes[next].view)
          buttons.current[next]?.focus()
        }}>
        <Icon size={17} aria-hidden="true" /><span>{label}</span>{mode === 'text-to-image' ? <small className="image-studio-mode-note" aria-hidden="true">仅草稿</small> : null}
      </button>)}
    </div>
  </header>
}
