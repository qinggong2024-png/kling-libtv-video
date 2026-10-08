import type { ReactNode } from 'react'
import { Image } from 'lucide-react'
import { LocalImage } from '../Media'

export function AssetCard({ name, file, selected = false, disabled = false, onSelect, children }: {
  name: string
  file?: File
  selected?: boolean
  disabled?: boolean
  onSelect: () => void
  children?: ReactNode
}) {
  return <article className={`studio-asset-card${selected ? ' is-selected' : ''}`}>
    <button type="button" className="studio-asset-card__select" onClick={onSelect} disabled={disabled} aria-pressed={selected} aria-label={`选择${name}`}>
      <span className="studio-asset-card__media">{file ? <LocalImage file={file} alt={name} /> : <Image size={22} aria-hidden="true" />}</span>
      <strong title={name}>{name}</strong>
    </button>
    {children}
  </article>
}
