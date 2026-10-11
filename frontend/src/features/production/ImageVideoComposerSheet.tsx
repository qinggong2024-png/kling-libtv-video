// 本文件由 App.tsx 拆分生成（2026-09-28 前端架构拆分 v2）。
// 代码为逐字搬运，未经逻辑改写。
import { X } from 'lucide-react'
import { useEffect } from 'react'
import { createPortal } from 'react-dom'
import { type SystemStatus, type Task } from '../../types'
import { VideoStudio as ProductionComposer } from '../video-studio'
import { type RemixSeed } from './productionTypes'

export function ImageVideoComposerSheet({ seed, system, actorId, onClose, onCreated }: {
  seed: RemixSeed
  system: SystemStatus | null
  actorId: string | null
  onClose: () => void
  onCreated: (task: Task) => void
}) {
  useEffect(() => {
    document.body.classList.add('modal-open')
    return () => document.body.classList.remove('modal-open')
  }, [])

  return createPortal(<div className="image-composer-sheet-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
    <section className="image-composer-sheet" role="dialog" aria-modal="true" aria-labelledby="image-composer-sheet-title">
      <header><div><span>图片中心</span><h2 id="image-composer-sheet-title">视频制作</h2></div><button type="button" className="icon-button" onClick={onClose} aria-label="关闭视频制作" title="关闭"><X size={18} /></button></header>
      <div className="image-composer-sheet__body"><ProductionComposer key={seed.id} seed={seed} system={system} actorId={actorId} onCreated={onCreated} /></div>
    </section>
  </div>, document.body)
}
