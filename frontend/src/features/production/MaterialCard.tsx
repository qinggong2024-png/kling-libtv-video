// 本文件由 App.tsx 拆分生成（2026-09-28 前端架构拆分 v2）。
// 代码为逐字搬运，未经逻辑改写。
import { X } from 'lucide-react'
import { useRef } from 'react'
import { type Material, type UploadBucket } from './productionTypes'
import { LocalImage } from '../../shared/components/Media'

export const MATERIAL_DRAG_TYPE = 'application/x-kling-api-material'

export function MaterialCard({ material, bucket, index, onRemove, onDropAt, onPreview }: {
  material: Material
  bucket: UploadBucket
  index: number
  onRemove: () => void
  onDropAt: (event: React.DragEvent, target: number) => void
  onPreview: () => void
}) {
  const dragStartedRef = useRef(false)
  return <article
    className="material-card"
    title={material.file.name}
    draggable
    onDragStart={(event) => {
      dragStartedRef.current = true
      event.dataTransfer.effectAllowed = 'move'
      event.dataTransfer.setData(MATERIAL_DRAG_TYPE, material.id)
      event.dataTransfer.setData('text/material-bucket', bucket)
      event.currentTarget.classList.add('is-dragging')
    }}
    onDragEnd={(event) => {
      event.currentTarget.classList.remove('is-dragging')
      window.setTimeout(() => { dragStartedRef.current = false }, 0)
    }}
    onDragOver={(event) => {
      event.preventDefault()
      event.dataTransfer.dropEffect = event.dataTransfer.types.includes(MATERIAL_DRAG_TYPE) ? 'move' : 'copy'
    }}
    onDrop={(event) => onDropAt(event, index)}
  >
    <div className="material-preview">
      <div
        role="button"
        tabIndex={0}
        className="material-preview-trigger"
        onClick={() => {
          if (!dragStartedRef.current) onPreview()
        }}
        onKeyDown={(event) => {
          if (event.key !== 'Enter' && event.key !== ' ') return
          event.preventDefault()
          if (!dragStartedRef.current) onPreview()
        }}
        aria-label={`查看图片 ${index + 1} 大图`}
        title="点击查看大图，长按拖拽排序"
      >
        <LocalImage file={material.file} alt={material.file.name} />
      </div>
      <span className="order-index">{index + 1}</span>
      <button
        type="button"
        className="material-remove"
        onClick={(event) => {
          event.stopPropagation()
          onRemove()
        }}
        onPointerDown={(event) => event.stopPropagation()}
        aria-label={`删除图片 ${index + 1}`}
        title="删除图片"
      >
        <X size={14} strokeWidth={2.25} />
      </button>
    </div>
  </article>
}
