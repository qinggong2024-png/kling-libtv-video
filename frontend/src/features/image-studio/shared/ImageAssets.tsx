import { Check, Image as ImageIcon, UploadCloud, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent, DragEvent, ReactNode } from 'react'
import { IMAGE_FILE_ACCEPT, isSupportedImageFile } from '../../../imageFiles'
import { fetchAssetObjectUrl } from '../../../api'
import { IMAGE_ASSET_SLOT_LABELS, getImageAssetSlots, imageAssetSetFromSlots, moveImageAssetSlot } from '../../../imageCenterModel'
import type { ImageAssetSet, OutfitDraft } from '../../../imageCenterModel'
const ASSET_SLOT_DRAG_TYPE = 'application/x-image-center-slot'

function useFileUrl(file: File | null): string {
  const [url, setUrl] = useState('')
  useEffect(() => {
    let active = true
    if (!file) {
      queueMicrotask(() => { if (active) setUrl('') })
      return () => { active = false }
    }
    const nextUrl = URL.createObjectURL(file)
    queueMicrotask(() => { if (active) setUrl(nextUrl) })
    return () => {
      active = false
      URL.revokeObjectURL(nextUrl)
    }
  }, [file])
  return url
}

export function AssetPreview({ file, url = '', alt }: { file: File | null; url?: string; alt: string }) {
  const source = useFileUrl(file) || url
  return source ? <img src={source} alt={alt} draggable={false} /> : <ImageIcon aria-hidden="true" size={22} />
}

export function AuthenticatedAssetPreview({ file, url, alt }: { file: File | null; url: string; alt: string }) {
  const [authenticatedUrl, setAuthenticatedUrl] = useState('')
  useEffect(() => {
    let active = true
    let objectUrl = ''
    if (!url || file) {
      queueMicrotask(() => { if (active) setAuthenticatedUrl('') })
      return () => { active = false }
    }
    void fetchAssetObjectUrl(url).then((nextUrl) => {
      objectUrl = nextUrl
      if (active) setAuthenticatedUrl(nextUrl)
      else URL.revokeObjectURL(nextUrl)
    }).catch(() => {
      if (active) setAuthenticatedUrl('')
    })
    return () => {
      active = false
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [file, url])
  return <AssetPreview file={file} url={authenticatedUrl} alt={alt} />
}

export function OrderedAssetUpload({ idPrefix, title, description, headerAccessory, assets, onChange }: {
  idPrefix: string
  title: string
  description: string
  headerAccessory?: ReactNode
  assets: ImageAssetSet
  onChange: (assets: ImageAssetSet) => void
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const files = getImageAssetSlots(assets).filter((file): file is File => file !== null)
  const count = files.length
  const receive = (files: File[]) => {
    const accepted = files.filter(isSupportedImageFile)
    if (!accepted.length) return
    onChange(imageAssetSetFromSlots([...getImageAssetSlots(assets).filter((file): file is File => file !== null), ...accepted].slice(0, 3)))
  }
  const change = (event: ChangeEvent<HTMLInputElement>) => {
    receive(Array.from(event.currentTarget.files ?? []))
    event.currentTarget.value = ''
  }
  const remove = (index: number) => {
    onChange(imageAssetSetFromSlots(files.filter((_, fileIndex) => fileIndex !== index)))
  }
  const move = (from: number, to: number) => onChange(moveImageAssetSlot(assets, from, to))
  const handleDrop = (event: DragEvent, target: number) => {
    event.preventDefault()
    event.stopPropagation()
    const slotPayload = event.dataTransfer.getData(ASSET_SLOT_DRAG_TYPE)
    if (slotPayload) {
      try {
        const source = JSON.parse(slotPayload) as { owner?: string; index?: number }
        if (source.owner === idPrefix && source.index !== undefined && Number.isInteger(source.index)) move(source.index, target)
      } catch {
        // Ignore malformed drag data from outside this uploader.
      }
      return
    }
    receive(Array.from(event.dataTransfer.files))
  }

  return <section
    className={`ordered-asset-upload asset-count-${count}${count ? ' has-files' : ''}${headerAccessory ? ' has-header-accessory' : ''}`}
    aria-label={title}
    onDragOver={(event) => {
      event.preventDefault()
      event.dataTransfer.dropEffect = event.dataTransfer.types.includes(ASSET_SLOT_DRAG_TYPE) ? 'move' : 'copy'
    }}
    onDrop={(event) => {
      handleDrop(event, files.length)
    }}
  >
    <header>
      <div className="ordered-asset-upload__title"><strong>{title}</strong><small>{description}</small></div>
      <span>{count}/3</span>
    </header>
    {headerAccessory}
    <button type="button" className="ordered-asset-dropzone" disabled={count >= 3} onClick={() => inputRef.current?.click()}>
      <span><UploadCloud size={20} /></span>
      <span><strong>{count ? '继续添加图片' : '拖拽或点击批量上传'}</strong><small>JPG、PNG、WEBP，最多 3 张</small></span>
    </button>
    <div className="ordered-asset-slot-guide" aria-label={`${title}上传槽位说明`}>
      {IMAGE_ASSET_SLOT_LABELS.map((label, index) => <span key={label} className={files[index] ? 'is-filled' : index === 0 ? 'is-required' : 'is-optional'}>
        <strong>{index + 1} · {label}</strong>
        <small>{files[index] ? '已上传' : index === 0 ? '必填' : '可选'}</small>
      </span>)}
    </div>
    {files.length ? <div className="ordered-asset-list" aria-label={`${title}排序列表`}>
      {files.map((file, index) => <article
        key={`${idPrefix}-${index}-${file.name}-${file.size}-${file.lastModified}`}
        className="ordered-asset-card"
        title={`${IMAGE_ASSET_SLOT_LABELS[index]}：${file.name}`}
        draggable
        onDragStart={(event) => {
          event.dataTransfer.effectAllowed = 'move'
          event.dataTransfer.setData(ASSET_SLOT_DRAG_TYPE, JSON.stringify({ owner: idPrefix, index }))
          event.currentTarget.classList.add('is-dragging')
        }}
        onDragEnd={(event) => event.currentTarget.classList.remove('is-dragging')}
        onDragOver={(event) => {
          event.preventDefault()
          event.dataTransfer.dropEffect = event.dataTransfer.types.includes(ASSET_SLOT_DRAG_TYPE) ? 'move' : 'copy'
        }}
        onDrop={(event) => handleDrop(event, index)}
      >
        <span className="ordered-asset-card__media"><AssetPreview file={file} alt={`${IMAGE_ASSET_SLOT_LABELS[index]}：${file.name}`} /></span>
        <span className="ordered-asset-card__role"><i>{index + 1}</i>{IMAGE_ASSET_SLOT_LABELS[index]}{index === 0 ? <small>必填</small> : null}</span>
        <button type="button" className="ordered-asset-card__remove" onClick={(event) => { event.stopPropagation(); remove(index) }} onPointerDown={(event) => event.stopPropagation()} aria-label={`移除${IMAGE_ASSET_SLOT_LABELS[index]}`} title="删除图片"><X size={14} /></button>
      </article>)}
    </div> : null}
    <input ref={inputRef} id={`${idPrefix}-files`} className="sr-only" type="file" multiple accept={IMAGE_FILE_ACCEPT} disabled={count >= 3} onChange={change} />
  </section>
}

export function OutfitCard({ outfit, index, onChange }: {
  outfit: OutfitDraft
  index: number
  onChange: (outfit: OutfitDraft) => void
}) {
  return <article className="outfit-card">
    <OrderedAssetUpload
      idPrefix={outfit.id}
      title="产品图片"
      description="本套商品按正面、背面、侧面排列；正面必填"
      headerAccessory={<div className="outfit-card__meta">
        <span className="outfit-card__number">{String(index + 1).padStart(2, '0')}</span>
        <label><span>套装名称</span><input value={outfit.name} maxLength={80} title="套装名称" onChange={(event) => onChange({ ...outfit, name: event.target.value })} /></label>
        <label><span>商品 SKU</span><input value={outfit.sku} maxLength={80} title="商品 SKU" placeholder="SKU（可选）" onChange={(event) => onChange({ ...outfit, sku: event.target.value })} /></label>
      </div>}
      assets={outfit}
      onChange={(assets) => onChange({ ...outfit, ...assets })}
    />
  </article>
}

export function OutfitNavItem({ outfit, index, selected, canRemove, onSelect, onRemove }: {
  outfit: OutfitDraft
  index: number
  selected: boolean
  canRemove: boolean
  onSelect: () => void
  onRemove: () => void
}) {
  return <div className={`outfit-nav-entry${selected ? ' is-selected' : ''}`}>
    <button
      type="button"
      id={`outfit-tab-${outfit.id}`}
      className="outfit-nav-item"
      role="tab"
      aria-selected={selected}
      aria-controls="active-outfit-editor"
      onClick={onSelect}
    >
      <span className="outfit-nav-item__thumb"><AssetPreview file={outfit.front} alt={outfit.front ? `${outfit.name}正面图` : ''} /></span>
      <span><strong>{outfit.name.trim() || `套装 ${String(index + 1).padStart(2, '0')}`}</strong><small>{outfit.sku.trim() || `第 ${index + 1} 套产品`}</small></span>
      <i className={outfit.front ? 'is-ready' : ''}>{outfit.front ? <Check size={12} /> : index + 1}</i>
    </button>
    {canRemove ? <button type="button" className="outfit-nav-remove" onClick={onRemove} aria-label={`删除${outfit.name}`} title="删除套装"><X size={14} /></button> : null}
  </div>
}

