import { ArrowLeft, ArrowRight, Film } from 'lucide-react'
import type { Material } from '../../../features/production/productionTypes'
import { MaterialCard } from '../../../features/production/MaterialCard'
import { IconButton } from '../ui/Button'

export function ShotCard({ material, index, selected, disabled, canMoveForward, onPreview, onRemove, onDropAt, onMove }: {
  material: Material
  index: number
  selected: boolean
  disabled: boolean
  canMoveForward: boolean
  onPreview: () => void
  onRemove: () => void
  onDropAt: (event: React.DragEvent, target: number) => void
  onMove: (offset: number) => void
}) {
  return <div className={`studio-shot${selected ? ' is-selected' : ''}`}>
    <MaterialCard material={material} index={index} bucket="storyboard" readOnly={disabled} onRemove={onRemove} onDropAt={onDropAt} onPreview={onPreview} />
    <span className="studio-shot__name" title={material.file.name}>{material.file.name}</span>
    <div className="studio-shot-actions"><IconButton label={`前移分镜 ${index + 1}`} disabled={disabled || index === 0} onClick={() => onMove(-1)}><ArrowLeft size={14} /></IconButton><IconButton label={`后移分镜 ${index + 1}`} disabled={disabled || !canMoveForward} onClick={() => onMove(1)}><ArrowRight size={14} /></IconButton></div>
  </div>
}

export function Storyboard({ materials, selectedId, disabled = false, onSelect, onMove, onRemove, onDropAt, onPreview }: {
  materials: Material[]
  selectedId?: string
  disabled?: boolean
  onSelect: (id: string) => void
  onMove: (id: string, offset: number) => void
  onRemove: (id: string) => void
  onDropAt: (event: React.DragEvent, target: number) => void
  onPreview: (material: Material, index: number) => void
}) {
  return <section className="studio-storyboard" aria-label="分镜序列">
    <header><h2><Film size={16} aria-hidden="true" />分镜序列</h2><span>{materials.length} 张</span></header>
    {materials.length ? <div className="studio-storyboard__track" aria-label="分镜图排序列表">{materials.map((material, index) => <ShotCard key={material.id} material={material} index={index} selected={material.id === selectedId} disabled={disabled} canMoveForward={index < materials.length - 1} onPreview={() => { onSelect(material.id); onPreview(material, index) }} onRemove={() => onRemove(material.id)} onDropAt={onDropAt} onMove={(offset) => onMove(material.id, offset)} />)}</div>
      : <div className="studio-storyboard__empty">暂无分镜</div>}
  </section>
}
