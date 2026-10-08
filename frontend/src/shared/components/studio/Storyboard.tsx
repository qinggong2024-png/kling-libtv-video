import { ArrowLeft, ArrowRight, Film } from 'lucide-react'
import type { Material } from '../../../features/production/productionTypes'
import { AssetCard } from '../assets/AssetCard'
import { IconButton } from '../ui/Button'

export function ShotCard({ material, index, selected, disabled, canMoveForward, onSelect, onMove }: {
  material: Material
  index: number
  selected: boolean
  disabled: boolean
  canMoveForward: boolean
  onSelect: () => void
  onMove: (offset: number) => void
}) {
  return <AssetCard name={`分镜 ${index + 1}`} file={material.file} selected={selected} onSelect={onSelect}>
    <div className="studio-shot-actions"><IconButton label={`前移分镜 ${index + 1}`} disabled={disabled || index === 0} onClick={() => onMove(-1)}><ArrowLeft size={14} /></IconButton><IconButton label={`后移分镜 ${index + 1}`} disabled={disabled || !canMoveForward} onClick={() => onMove(1)}><ArrowRight size={14} /></IconButton></div>
  </AssetCard>
}

export function Storyboard({ materials, selectedId, disabled = false, onSelect, onMove }: {
  materials: Material[]
  selectedId?: string
  disabled?: boolean
  onSelect: (id: string) => void
  onMove: (id: string, offset: number) => void
}) {
  return <section className="studio-storyboard" aria-label="分镜序列">
    <header><h2><Film size={16} aria-hidden="true" />分镜序列</h2><span>{materials.length} 张</span></header>
    {materials.length ? <div className="studio-storyboard__track">{materials.map((material, index) => <ShotCard key={material.id} material={material} index={index} selected={material.id === selectedId} disabled={disabled} canMoveForward={index < materials.length - 1} onSelect={() => onSelect(material.id)} onMove={(offset) => onMove(material.id, offset)} />)}</div>
      : <div className="studio-storyboard__empty">暂无分镜</div>}
  </section>
}
