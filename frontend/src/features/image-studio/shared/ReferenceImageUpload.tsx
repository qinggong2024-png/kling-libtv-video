import { ArrowLeft, ArrowRight, GripVertical, UploadCloud, X } from 'lucide-react'
import { useRef, useState } from 'react'
import type { DragEvent } from 'react'
import { IMAGE_FILE_ACCEPT, isSupportedImageFile } from '../../../imageFiles'
import { IMAGE_REFERENCE_ROLE_ORDER } from '../../../imageCenterModel'
import type { ImageReferenceRole } from '../../../imageCenterModel'
import { AssetPreview } from './ImageAssets'

const REFERENCE_DRAG_TYPE = 'application/x-image-studio-reference'
const REFERENCE_ROLE_LABELS: Record<ImageReferenceRole, string> = {
  'model.front': '模特正面', 'product.front': '商品正面', 'product.back': '商品背面',
  'model.back': '模特背面', 'product.side': '商品侧面', 'model.side': '模特侧面',
}

export function ReferenceImageUpload({ files, boundRoles, maxFiles, onChange, onPreview }: {
  files: File[]
  boundRoles: readonly ImageReferenceRole[]
  maxFiles: number
  onChange: (files: File[]) => void
  onPreview: (file: File, label: string) => void
}) {
  const input = useRef<HTMLInputElement>(null)
  const [notice, setNotice] = useState('')
  const [dropTarget, setDropTarget] = useState<number | null>(null)
  const receive = (incoming: File[]) => {
    const accepted = incoming.filter(isSupportedImageFile)
    const available = Math.max(0, maxFiles - files.length)
    const added = accepted.slice(0, available)
    if (added.length) onChange([...files, ...added])
    setNotice(accepted.length > available ? `当前模型最多支持 ${maxFiles} 张参考图，超出的图片未添加。`
      : accepted.length !== incoming.length ? '仅支持 JPG、PNG、WEBP 图片，其他文件未添加。' : '')
  }
  const move = (from: number, target: number) => {
    const to = Math.min(target, files.length - 1)
    if (!Number.isInteger(from) || from < 0 || from >= files.length || to < 0 || from === to) return
    const next = [...files]
    const [file] = next.splice(from, 1)
    next.splice(to, 0, file)
    onChange(next)
    setNotice('')
  }
  const drop = (event: DragEvent, target: number) => {
    event.preventDefault()
    event.stopPropagation()
    setDropTarget(null)
    const source = event.dataTransfer.getData(REFERENCE_DRAG_TYPE)
    if (source) {
      if (/^\d+$/.test(source)) move(Number(source), target)
      return
    }
    receive(Array.from(event.dataTransfer.files))
  }
  return <section className="image-reference-upload" aria-label="参考图片"
    onDragOver={event => { event.preventDefault(); event.dataTransfer.dropEffect = event.dataTransfer.types.includes(REFERENCE_DRAG_TYPE) ? 'move' : 'copy' }}
    onDrop={event => drop(event, files.length)}>
    <header><h3>上传参考图片</h3><span>{files.length}/{maxFiles} 张</span></header>
    <button type="button" className="image-reference-upload__dropzone" disabled={files.length >= maxFiles} onClick={() => input.current?.click()}>
      <UploadCloud size={22} aria-hidden="true" /><span><strong>{files.length ? '添加图片' : '上传图片'}</strong><small>先上传模特正面和商品正面 · JPG、PNG、WEBP · 最多 {maxFiles} 张</small></span>
    </button>
    <input ref={input} id="image-reference-files" className="sr-only" type="file" multiple accept={IMAGE_FILE_ACCEPT}
      disabled={files.length >= maxFiles} onChange={event => { receive(Array.from(event.currentTarget.files ?? [])); event.currentTarget.value = '' }} />
    <ol className="image-reference-position-guide" aria-label="参考图固定上传顺序">
      {IMAGE_REFERENCE_ROLE_ORDER.map((role, index) => <li key={role} className={index >= maxFiles ? 'is-outside-limit' : boundRoles.includes(role) ? 'is-filled' : ''}>
        <span>图{index + 1}</span><strong>{REFERENCE_ROLE_LABELS[role]}</strong><small>{index >= maxFiles ? '当前模型不支持' : index < 2 ? '必填' : '可选'}</small>
      </li>)}
    </ol>
    <p className="image-reference-upload__binding-note">当前用途见图片标签；上传、排序或删除后，按以上顺序重新绑定。</p>
    {files.length ? <div className="image-reference-list" role="list" aria-label="参考图顺序">
      {files.map((file, index) => <article key={`${index}-${file.name}-${file.size}-${file.lastModified}`}
        role="listitem" aria-label={`参考图 ${index + 1}`} className={`image-reference-tile${dropTarget === index ? ' is-drop-target' : ''}`}
        draggable onDragStart={event => { event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData(REFERENCE_DRAG_TYPE, String(index)) }}
        onDragEnd={() => setDropTarget(null)}
        onDragOver={event => { event.preventDefault(); event.stopPropagation(); setDropTarget(index) }}
        onDragLeave={() => setDropTarget(null)} onDrop={event => drop(event, index)}>
        <button type="button" className="image-reference-tile__preview" onClick={() => onPreview(file, `参考图 ${index + 1}`)} aria-label={`查看参考图 ${index + 1}`} title={file.name}>
          <AssetPreview file={file} alt={`图 ${index + 1}：${file.name}`} />
        </button>
        <div className="image-reference-tile__binding"><strong>图{index + 1} · {REFERENCE_ROLE_LABELS[boundRoles[index]] ?? '用途未提供'}</strong><small title={file.name}>{file.name}</small></div>
        <div className="image-reference-tile__toolbar"><span aria-hidden="true" title="拖拽排序"><GripVertical size={13} /></span>
          <button type="button" disabled={index === 0} onClick={() => move(index, index - 1)} aria-label={`前移参考图 ${index + 1}`} title="前移"><ArrowLeft size={13} /></button>
          <button type="button" disabled={index === files.length - 1} onClick={() => move(index, index + 1)} aria-label={`后移参考图 ${index + 1}`} title="后移"><ArrowRight size={13} /></button>
          <button type="button" onClick={() => { onChange(files.filter((_, position) => position !== index)); setNotice('') }} aria-label={`删除参考图 ${index + 1}`} title="删除"><X size={14} /></button>
        </div>
      </article>)}
    </div> : null}
    {notice ? <p className="image-reference-upload__notice" role="status">{notice}</p> : null}
  </section>
}
