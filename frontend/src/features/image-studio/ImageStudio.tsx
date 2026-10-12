import {
  AlertTriangle, Check, CheckCircle2, ChevronDown, ChevronRight, ChevronUp, Clock3, Columns2, Film, GripVertical,
  Download, Image as ImageIcon, Images, Layers3, LoaderCircle, Package, Plus, RotateCcw, Save, Shirt,
  Sparkles, UploadCloud, UserRound, WandSparkles, X,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { ChangeEvent, DragEvent, ReactNode } from 'react'
import { createPortal } from 'react-dom'

import { IMAGE_FILE_ACCEPT, isSupportedImageFile } from '../../imageFiles'
import { ApiError, createImageGenerationBatch, fetchAssetObjectUrl, getImageGenerationBatch, querySubmissionRecovery, saveAsset, setImageOutputQualityDecision } from '../../api'
import { CustomPromptField } from '../../CustomPromptField'
import {
  IMAGE_ASSET_SLOT_LABELS, MAX_IMAGE_CENTER_OUTFITS,
  buildImageGenerationBatchRequest, buildWaitingTasks, calculateImageTaskSummary, compactImageAssetSet,
  createImageCenterDraft, createImageCenterRegenerationDraft, createOutfit, getImageAssetSlots, getOrderedSelectedTasks, imageAssetSetFromSlots,
  moveImageAssetSlot, normalizeImageGenerationModes, normalizeImageGenerationQuality, parseStoryboardPrompt, validateImageCenterDraft,
} from '../../imageCenterModel'
import type { ImageGenerationBatch, ImageGenerationBatchItem } from '../../types'
import type {
  ImageAssetSet, ImageCenterDraft, ImageGenerationMode, ImageGenerationOutput,
  ImageGenerationTask, ImageProvider, OutfitDraft,
} from '../../imageCenterModel'
import { loadImageCenterDraft, saveImageCenterDraft } from '../../imageCenterStore'
import { createUuid } from '../../uuid'
import { imageTaskNotificationForTransition } from '../../browserNotifications'
import { FoundationDrawer } from '../../shared/components/ui'
import { imageStatusPresentation } from '../../domain/statusPresentation'
import { DirectorStudio } from '../director-studio/DirectorStudio'
import '../image-center/imageReview.css'

import type {
  ImageCenterNotificationEvent,
  ImageCenterProps,
} from './contracts'

export type {
  ImageCenterNotificationEvent,
  ImageCenterProps,
  ImageCenterVideoHandoff,
  VideoSubjectSource,
} from './contracts'

const ASSET_SLOT_DRAG_TYPE = 'application/x-image-center-slot'
const IMAGE_OUTPUT_DRAG_TYPE = 'application/x-image-center-output'
const TERMINAL_IMAGE_STATUSES = new Set(['completed', 'failed', 'write_uncertain'])
type GenerationAvailability = 'checking' | 'available' | 'unavailable'

function isGenerationUnavailableError(cause: unknown): boolean {
  return cause instanceof ApiError
    && (cause.code === 'MAINTENANCE_QUERY_ONLY' || cause.status === 503 || cause.status === 403)
}

function generationUnavailableMessage(cause: unknown): string {
  if (cause instanceof ApiError && cause.code === 'MAINTENANCE_QUERY_ONLY') return '当前处于维护模式，仅支持登录和查询已保存任务，生成暂不可用。'
  if (cause instanceof ApiError && cause.status === 403) return '当前账号暂无生图权限，生成任务暂不可用，请联系管理员。'
  return '当前无法使用生图服务，创建任务已暂停，请稍后再试或联系管理员。'
}

function localTaskStatus(status: ImageGenerationBatchItem['status']) {
  return status
}

function mergeBatchIntoTasks(tasks: ImageGenerationTask[], batch: ImageGenerationBatch): ImageGenerationTask[] {
  const items = new Map(batch.items.map((item) => [item.clientTaskId, item]))
  return tasks.map((task) => {
    if (task.batchId !== batch.id && !items.has(task.id)) return task
    const item = items.get(task.id)
    if (!item) return task
    return {
      ...task,
      batchId: batch.id,
      clientBatchId: batch.clientBatchId ?? task.clientBatchId ?? null,
      providerTaskId: item.providerTaskId,
      providerTaskIds: item.providerTaskIds ?? (item.providerTaskId ? [item.providerTaskId] : []),
      modelId: item.modelId || task.modelId,
      status: localTaskStatus(item.status),
      outputs: item.outputs.map((output) => ({
        ...output,
        file: null,
        url: output.downloadUrl || output.url,
      })),
      error: item.error?.message ?? '',
      errorCode: item.error?.code ?? null,
      retryable: item.error?.retryable ?? null,
      errorDetails: item.error?.details,
    }
  })
}

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

function AssetPreview({ file, url = '', alt }: { file: File | null; url?: string; alt: string }) {
  const source = useFileUrl(file) || url
  return source ? <img src={source} alt={alt} draggable={false} /> : <ImageIcon aria-hidden="true" size={22} />
}

function AuthenticatedAssetPreview({ file, url, alt }: { file: File | null; url: string; alt: string }) {
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

function OrderedAssetUpload({ idPrefix, title, description, headerAccessory, assets, onChange }: {
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
      {headerAccessory}
      <span>{count}/3</span>
    </header>
    <button type="button" className="ordered-asset-dropzone" disabled={count >= 3} onClick={() => inputRef.current?.click()}>
      <span><UploadCloud size={20} /></span>
      <span><strong>{count ? '继续添加图片' : '拖拽或点击批量上传'}</strong><small>JPG、PNG、WEBP，最多 3 张</small></span>
    </button>
    <div className="ordered-asset-slot-guide" aria-label={`${title}上传槽位说明`}>
      {IMAGE_ASSET_SLOT_LABELS.map((label, index) => <span key={label} className={files[index] ? 'is-filled' : index === 0 ? 'is-required' : 'is-optional'}>
        <strong>{label}</strong>
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

function OutfitCard({ outfit, index, onChange }: {
  outfit: OutfitDraft
  index: number
  onChange: (outfit: OutfitDraft) => void
}) {
  return <article className="outfit-card">
    <OrderedAssetUpload
      idPrefix={outfit.id}
      title="产品图片"
      description="图二固定为球衣正面，图三固定为球衣背面；侧面为补充参考"
      headerAccessory={<div className="outfit-card__meta">
        <span className="outfit-card__number">{String(index + 1).padStart(2, '0')}</span>
        <label><span className="sr-only">套装名称</span><input value={outfit.name} maxLength={80} title="套装名称" onChange={(event) => onChange({ ...outfit, name: event.target.value })} /></label>
        <label><span className="sr-only">商品 SKU</span><input value={outfit.sku} maxLength={80} title="商品 SKU" placeholder="SKU（可选）" onChange={(event) => onChange({ ...outfit, sku: event.target.value })} /></label>
      </div>}
      assets={outfit}
      onChange={(assets) => onChange({ ...outfit, ...assets })}
    />
  </article>
}

function OutfitNavItem({ outfit, index, selected, canRemove, onSelect, onRemove }: {
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

function SourceThumb({ file, label, onPreview }: {
  file: File | null
  label: string
  onPreview: (file: File, label: string) => void
}) {
  return <figure className="image-task-source">
    <button
      type="button"
      disabled={!file}
      onClick={() => { if (file) onPreview(file, label) }}
      aria-label={file ? `查看${label}大图` : undefined}
      title={file ? '查看大图' : undefined}
    ><AssetPreview file={file} alt={file ? `${label}：${file.name}` : ''} /></button>
    <figcaption>{label}</figcaption>
  </figure>
}

function OutputSelectionButton({ selected, label, className, onToggle }: {
  selected: boolean
  label: string
  className: string
  onToggle: () => void
}) {
  return <button
    type="button"
    className={`${className}${selected ? ' is-selected' : ''}`}
    aria-label={selected ? `取消勾选${label}` : `勾选${label}`}
    aria-pressed={selected}
    title={selected ? '取消勾选' : '勾选图片'}
    onClick={(event) => { event.stopPropagation(); onToggle() }}
  >{selected ? <Check size={17} strokeWidth={2.6} /> : null}</button>
}

export function OutputCard({ taskId, output, selected, onToggle, onReject: onReview, onPreview }: {
  taskId: string
  output: ImageGenerationOutput
  selected: boolean
  onToggle: () => void
  onReject: () => void
  onPreview: () => void
}) {
  const download = () => {
    if (output.url) void saveAsset(output.downloadUrl || output.url, `${output.label}.png`)
  }
  return <article
    className={`image-output-card${selected ? ' is-selected' : ''}`}
    draggable
    onDragStart={(event) => {
      event.dataTransfer.effectAllowed = 'copyMove'
      event.dataTransfer.setData(IMAGE_OUTPUT_DRAG_TYPE, JSON.stringify({ taskId, outputId: output.id }))
      event.currentTarget.classList.add('is-dragging')
    }}
    onDragEnd={(event) => event.currentTarget.classList.remove('is-dragging')}
    title="拖入选片工作台"
  >
    <button type="button" className="image-output-card__preview" onClick={onPreview} aria-label={`查看${output.label}大图`} title="查看大图">
      <span className="image-output-card__media"><AuthenticatedAssetPreview file={output.file} url={output.url} alt={output.label} /></span>
      <span><strong>{output.label}</strong><small>{output.kind === 'fusion' ? '多图融合' : '分镜图'}</small></span>
    </button>
    <OutputSelectionButton selected={selected} label={output.label} className="image-output-card__selection" onToggle={onToggle} />
    <button type="button" className="image-output-card__reject" disabled={!output.qualificationStatus} onClick={(event) => { event.stopPropagation(); onReview() }} title={output.qualificationStatus ? '审核图片' : '服务端尚未启用图片审核'} aria-label={`审核${output.label}`}><CheckCircle2 size={14} /></button>
    <span className={`image-output-card__quality is-${(output.qualificationStatus ?? 'PENDING').toLowerCase()}`}>{output.qualificationStatus === 'QUALIFIED' ? '已合格' : output.qualificationStatus === 'REJECTED' ? '已拒绝' : '待人工审核'}</span>
    {output.url ? <button type="button" className="image-output-card__download" onClick={download} title="下载图片" aria-label={`下载${output.label}`}><Download size={14} /></button> : null}
  </article>
}

function AssetPreviewDialog({ file, url = '', label, selection, onClose }: {
  file: File | null
  url?: string
  label: string
  selection?: { selected: boolean; onToggle: () => void }
  onClose: () => void
}) {
  const dialogRef = useRef<HTMLElement>(null)
  const onCloseRef = useRef(onClose)
  useEffect(() => { onCloseRef.current = onClose }, [onClose])
  useEffect(() => {
    const previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCloseRef.current()
    }
    document.body.classList.add('modal-open')
    document.addEventListener('keydown', closeOnEscape)
    dialogRef.current?.focus()
    return () => {
      document.body.classList.remove('modal-open')
      document.removeEventListener('keydown', closeOnEscape)
      previouslyFocused?.focus()
    }
  }, [])

  return createPortal(<div
    className="image-output-preview-backdrop"
    onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}
  >
    <section ref={dialogRef} className="image-output-preview" role="dialog" aria-modal="true" aria-labelledby="image-output-preview-title" tabIndex={-1}>
      <h2 id="image-output-preview-title" className="sr-only">{label}大图预览</h2>
      <button type="button" className="image-output-preview__stage" onClick={onClose} aria-label={`关闭${label}大图预览`} title="关闭大图">
        <AuthenticatedAssetPreview file={file} url={url} alt={label} />
      </button>
      <button type="button" className="image-output-preview__close" onClick={onClose} aria-label="关闭大图预览" title="关闭大图"><X size={20} /></button>
      {selection ? <OutputSelectionButton selected={selection.selected} label={label} className="image-output-preview__selection" onToggle={selection.onToggle} /> : null}
    </section>
  </div>, document.body)
}

export function ImageOutputReview({ output, onSaved, onClose }: {
  output: ImageGenerationOutput
  onSaved: (values: Partial<ImageGenerationOutput>) => void
  onClose: () => void
}) {
  const [decision, setDecision] = useState<'QUALIFIED' | 'REJECTED'>('QUALIFIED')
  const [productPass, setProductPass] = useState(false)
  const [humanPass, setHumanPass] = useState(false)
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [uncertain, setUncertain] = useState(false)
  const startedAt = useRef(0)
  useEffect(() => { startedAt.current = performance.now() }, [])
  const submitting = useRef(false)
  const canSubmit = decision === 'QUALIFIED' ? productPass && humanPass : notes.trim().length > 0
  const save = async () => {
    if (!canSubmit || submitting.current || uncertain) return
    submitting.current = true
    setBusy(true)
    setError('')
    try {
      const result = await setImageOutputQualityDecision(output.id, {
        decision,
        productFidelityPass: decision === 'QUALIFIED' && productPass,
        humanCriticalPass: decision === 'QUALIFIED' && humanPass,
        humanReviewSeconds: Math.max(1, Math.round((performance.now() - startedAt.current) / 1000)),
        notes: notes.trim() || null,
      })
      onSaved(result)
      onClose()
    } catch (cause) {
      const unknown = !(cause instanceof ApiError) || cause.code === 'WRITE_UNCERTAIN' || cause.code === 'REQUEST_TIMEOUT' || cause.status >= 500
      setUncertain(unknown)
      setError(unknown ? '审核保存结果待确认，请刷新服务端记录核对，勿重复保存。' : cause instanceof Error ? cause.message : '图片审核保存失败')
    } finally {
      submitting.current = false
      setBusy(false)
    }
  }
  return <FoundationDrawer open title={`审核 · ${output.label}`} onClose={() => { if (!busy) onClose() }} footer={<>
    <button type="button" className="secondary-button" disabled={busy} onClick={onClose}>取消</button>
    <button type="button" className="primary-button" disabled={busy || uncertain || !canSubmit} onClick={() => void save()}>{busy ? <LoaderCircle size={16} className="spin" /> : <CheckCircle2 size={16} />}保存审核</button>
  </>}>
    <div className="image-review-media"><AuthenticatedAssetPreview file={output.file} url={output.url} alt={output.label} /></div>
    <fieldset className="image-review-fields" disabled={busy}>
      <legend>审核结果</legend>
      <label><input type="radio" name="image-review-decision" checked={decision === 'QUALIFIED'} onChange={() => setDecision('QUALIFIED')} />合格</label>
      <label><input type="radio" name="image-review-decision" checked={decision === 'REJECTED'} onChange={() => setDecision('REJECTED')} />退回</label>
      {decision === 'QUALIFIED' ? <>
        <label><input type="checkbox" checked={productPass} onChange={(event) => setProductPass(event.target.checked)} />商品颜色、图案、Logo、文字和服装结构一致</label>
        <label><input type="checkbox" checked={humanPass} onChange={(event) => setHumanPass(event.target.checked)} />人物与画面无关键缺陷</label>
      </> : null}
      <label htmlFor="image-review-notes">{decision === 'REJECTED' ? '退回原因（必填）' : '审核备注'}</label>
      <textarea id="image-review-notes" value={notes} onChange={(event) => setNotes(event.target.value)} maxLength={2000} rows={4} required={decision === 'REJECTED'} />
    </fieldset>
    {error ? <p role="alert" className="notice">{error}</p> : null}
  </FoundationDrawer>
}

function OutputPreview({ output, selected, onToggle, onClose }: {
  output: ImageGenerationOutput
  selected: boolean
  onToggle: () => void
  onClose: () => void
}) {
  return <AssetPreviewDialog
    file={output.file}
    url={output.url}
    label={output.label}
    selection={{ selected, onToggle }}
    onClose={onClose}
  />
}

export function ImageOutputCompare({ outputs, onClose }: {
  outputs: ImageGenerationOutput[]
  onClose: () => void
}) {
  if (outputs.length < 2) return null
  const [left, right] = outputs
  return <FoundationDrawer
    open
    title="并排比较"
    eyebrow="只读比较"
    onClose={onClose}
  >
    <div className="image-compare-grid" aria-label="图片并排比较">
      {[left, right].map((output) => <article className="image-compare-panel" key={output.id}>
        <div className="image-compare-panel__media">
          <AuthenticatedAssetPreview file={output.file} url={output.url} alt={output.label} />
        </div>
        <div className="image-compare-panel__meta">
          <strong>{output.label}</strong>
          <span>{output.kind === 'fusion' ? '多图融合' : '分镜图'} · {output.view === 'shot' ? '镜头' : output.view === 'front' ? '正面' : '背面'}</span>
          <span>{output.qualificationStatus === 'QUALIFIED' ? '已合格' : output.qualificationStatus === 'REJECTED' ? '已拒绝' : '待人工审核'}</span>
        </div>
      </article>)}
    </div>
  </FoundationDrawer>
}

function SelectionWorkbench({ tasks, selectedOutputIds, expanded, preparing, onExpandedChange, onClear, onRemove, onPlaceOutput, onGenerate }: {
  tasks: ImageGenerationTask[]
  selectedOutputIds: string[]
  expanded: boolean
  preparing: boolean
  onExpandedChange: (expanded: boolean) => void
  onClear: () => void
  onRemove: (outputId: string) => void
  onPlaceOutput: (taskId: string, outputId: string, beforeOutputId?: string) => void
  onGenerate: () => void
}) {
  const selectedTasks = useMemo(() => getOrderedSelectedTasks(tasks, selectedOutputIds), [selectedOutputIds, tasks])
  const [dropActive, setDropActive] = useState(false)
  const parseOutputDrop = (event: DragEvent) => {
    const payload = event.dataTransfer.getData(IMAGE_OUTPUT_DRAG_TYPE)
    if (!payload) return null
    try {
      const parsed = JSON.parse(payload) as { taskId?: string; outputId?: string }
      return parsed.taskId && parsed.outputId ? { taskId: parsed.taskId, outputId: parsed.outputId } : null
    } catch { return null }
  }
  const dropOutput = (event: DragEvent, beforeOutputId?: string) => {
    event.preventDefault()
    event.stopPropagation()
    setDropActive(false)
    const payload = parseOutputDrop(event)
    if (payload) onPlaceOutput(payload.taskId, payload.outputId, beforeOutputId)
  }

  return <section
    className={`image-selection-bar${expanded ? ' is-expanded' : ''}${dropActive ? ' is-drop-active' : ''}`}
    aria-label="选片工作台"
    onDragEnter={(event) => {
      if (!event.dataTransfer.types.includes(IMAGE_OUTPUT_DRAG_TYPE)) return
      event.preventDefault()
      setDropActive(true)
    }}
    onDragOver={(event) => {
      if (!event.dataTransfer.types.includes(IMAGE_OUTPUT_DRAG_TYPE)) return
      event.preventDefault()
      event.dataTransfer.dropEffect = 'move'
    }}
    onDragLeave={(event) => {
      if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDropActive(false)
    }}
    onDrop={(event) => dropOutput(event)}
  >
    <div className="image-selection-bar__header" role="toolbar" aria-label="已选图片操作">
      <div className="image-selection-bar__summary" aria-live="polite">
        <span className="image-selection-bar__count" aria-hidden="true">{selectedOutputIds.length}</span>
        <span className="image-selection-bar__copy"><strong>已选择 {selectedOutputIds.length} 张图片</strong><small>{selectedTasks.length} 套产品可生成视频</small></span>
      </div>
      <button type="button" className="icon-button image-selection-bar__toggle" onClick={() => onExpandedChange(!expanded)} aria-expanded={expanded} aria-controls="image-selection-details" aria-label={expanded ? '收起选片详情' : '展开选片详情'} title={expanded ? '收起详情' : '展开详情'}>{expanded ? <ChevronDown size={18} /> : <ChevronUp size={18} />}</button>
      <div className="image-selection-bar__actions">
        <button type="button" className="secondary-button" onClick={onClear}><X size={16} />取消选择</button>
        <button type="button" className="primary-button" disabled={preparing} onClick={onGenerate}>{preparing ? <LoaderCircle className="spin" size={17} /> : <Film size={17} />}{preparing ? '正在准备' : '送入视频队列'}</button>
      </div>
    </div>
    <div id="image-selection-details" className="image-selection-bar__details" aria-hidden={!expanded} inert={!expanded}>
      <div className="image-selection-bar__details-inner">
        <header><div><strong>分镜编排</strong><small>共 {selectedTasks.length} 个产品视频</small></div><span>{selectedOutputIds.length} / {selectedTasks.length * 6} 张</span></header>
        <div className="image-selection-groups">{selectedTasks.map(({ task, outputs }) => <article key={task.id} className="image-selection-group">
          <div className="image-selection-frames" role="list" aria-label={`${task.outfitName}分镜顺序`} onDragOver={(event) => event.preventDefault()} onDrop={(event) => dropOutput(event)}>
            {outputs.map((output, index) => <article
              key={output.id}
              className="image-selection-frame"
              role="listitem"
              draggable
              onDragStart={(event) => {
                event.dataTransfer.effectAllowed = 'move'
                event.dataTransfer.setData(IMAGE_OUTPUT_DRAG_TYPE, JSON.stringify({ taskId: task.id, outputId: output.id }))
              }}
              onDragOver={(event) => { event.preventDefault(); event.stopPropagation(); event.dataTransfer.dropEffect = 'move' }}
              onDrop={(event) => dropOutput(event, output.id)}
            >
              <span><AuthenticatedAssetPreview file={output.file} url={output.url} alt={`${task.outfitName}分镜 ${index + 1}`} /></span>
              <i>{index + 1}</i>
              <button type="button" onClick={() => onRemove(output.id)} aria-label={`移除分镜 ${index + 1}`} title="移除分镜"><X size={12} /></button>
              <GripVertical size={13} aria-hidden="true" />
            </article>)}
            {outputs.length < 6 ? <div className="image-selection-drop-slot" aria-hidden="true"><Plus size={17} /><span>{outputs.length ? '添加分镜' : '暂无分镜'}</span></div> : null}
          </div>
          <div className="image-selection-product">
            <span><AssetPreview file={task.product.front} alt={`${task.outfitName}产品正面图`} /><i>产品</i></span>
            <div><strong>{task.outfitName}</strong><small>{task.sku || '未填写 SKU'}</small></div>
            <em>{outputs.length}/6</em>
          </div>
        </article>)}</div>
      </div>
    </div>
  </section>
}

export function ImageStudio(props: ImageCenterProps) {
  return <ScopedImageCenter key={props.draftScope ?? 'anonymous'} {...props} />
}

export function BatchImageOutputReview({ outputs, onSaved, onClose }: {
  outputs: ImageGenerationOutput[]
  onSaved: (outputId: string, values: Partial<ImageGenerationOutput>) => void
  onClose: () => void
}) {
  const [index, setIndex] = useState(0)
  const [decision, setDecision] = useState<'QUALIFIED' | 'REJECTED'>('QUALIFIED')
  const [productPass, setProductPass] = useState(false)
  const [humanPass, setHumanPass] = useState(false)
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [uncertain, setUncertain] = useState(false)
  const startedAt = useRef(0)
  const submitting = useRef(false)
  const output = outputs[index] ?? null
  useEffect(() => { startedAt.current = performance.now() }, [output?.id])
  if (!output) return null

  const canSubmit = decision === 'QUALIFIED' ? productPass && humanPass : notes.trim().length > 0
  const save = async () => {
    if (!canSubmit || submitting.current || uncertain) return
    submitting.current = true
    setBusy(true)
    setError('')
    try {
      const result = await setImageOutputQualityDecision(output.id, {
        decision,
        productFidelityPass: decision === 'QUALIFIED' && productPass,
        humanCriticalPass: decision === 'QUALIFIED' && humanPass,
        humanReviewSeconds: Math.max(1, Math.round((performance.now() - startedAt.current) / 1000)),
        notes: notes.trim() || null,
      })
      onSaved(output.id, result)
      if (index + 1 >= outputs.length) {
        onClose()
      } else {
        setIndex((current) => current + 1)
        setDecision('QUALIFIED')
        setProductPass(false)
        setHumanPass(false)
        setNotes('')
      }
    } catch (cause) {
      const unknown = !(cause instanceof ApiError) || cause.code === 'WRITE_UNCERTAIN' || cause.code === 'REQUEST_TIMEOUT' || cause.status >= 500
      setUncertain(unknown)
      setError(unknown ? '审核保存结果待确认，请刷新服务端记录核对，勿重复保存。' : cause instanceof Error ? cause.message : '图片审核保存失败')
    } finally {
      submitting.current = false
      setBusy(false)
    }
  }
  return <FoundationDrawer open title={`批量审核 · ${index + 1}/${outputs.length}`} onClose={() => { if (!busy) onClose() }} footer={<>
    <button type="button" className="secondary-button" disabled={busy} onClick={onClose}>取消</button>
    <button type="button" className="primary-button" disabled={busy || uncertain || !canSubmit} onClick={() => void save()}>{busy ? <LoaderCircle size={16} className="spin" /> : <CheckCircle2 size={16} />}{index + 1 >= outputs.length ? '保存并完成' : '保存并继续'}</button>
  </>}>
    <div className="image-review-progress" aria-live="polite"><strong>待审核图片</strong><span>{output.label}</span><small>完成当前项后自动进入下一张</small></div>
    <div className="image-review-media"><AuthenticatedAssetPreview file={output.file} url={output.url} alt={output.label} /></div>
    <fieldset className="image-review-fields" disabled={busy}>
      <legend>审核结果</legend>
      <label><input type="radio" name={`batch-image-review-decision-${output.id}`} checked={decision === 'QUALIFIED'} onChange={() => setDecision('QUALIFIED')} />合格</label>
      <label><input type="radio" name={`batch-image-review-decision-${output.id}`} checked={decision === 'REJECTED'} onChange={() => setDecision('REJECTED')} />退回</label>
      {decision === 'QUALIFIED' ? <>
        <label><input type="checkbox" checked={productPass} onChange={(event) => setProductPass(event.target.checked)} />商品颜色、图案、Logo、文字和服装结构一致</label>
        <label><input type="checkbox" checked={humanPass} onChange={(event) => setHumanPass(event.target.checked)} />人物与画面无关键缺陷</label>
      </> : null}
      <label htmlFor="batch-image-review-notes">{decision === 'REJECTED' ? '退回原因（必填）' : '审核备注'}</label>
      <textarea id="batch-image-review-notes" value={notes} onChange={(event) => setNotes(event.target.value)} maxLength={2000} rows={4} required={decision === 'REJECTED'} />
    </fieldset>
    {uncertain ? <p role="alert" className="notice image-review-uncertain">当前项保存状态未知，已停止批量审核，请刷新服务端记录核对，勿重复保存。</p> : error ? <p role="alert" className="notice">{error}</p> : null}
  </FoundationDrawer>
}

function ScopedImageCenter({ active, initialMode, draftScope, openTaskId, onPrepareVideos, onNotifications, onActiveTasksChange }: ImageCenterProps) {
  const [draft, setDraft] = useState<ImageCenterDraft>(() => createImageCenterDraft(createUuid(), createUuid()))
  const [activeOutfitId, setActiveOutfitId] = useState('')
  const [loaded, setLoaded] = useState(false)
  const [saveState, setSaveState] = useState<'saved' | 'saving' | 'error'>('saved')
  const [notice, setNotice] = useState('')
  const [preparingVideos, setPreparingVideos] = useState(false)
  const [selectionBarExpanded, setSelectionBarExpanded] = useState(false)
  const [previewOutputId, setPreviewOutputId] = useState<string | null>(null)
  const [previewSource, setPreviewSource] = useState<{ file: File; label: string } | null>(null)
  const [reviewOutputId, setReviewOutputId] = useState<string | null>(null)
  const [compareOpen, setCompareOpen] = useState(false)
  const [batchReviewOpen, setBatchReviewOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [generationAvailability, setGenerationAvailability] = useState<GenerationAvailability>('checking')
  const [generationAvailabilityReason, setGenerationAvailabilityReason] = useState('')
  const [studioMode, setStudioMode] = useState<'custom' | 'director'>(initialMode ?? 'custom')
  const saveTimerRef = useRef<number | null>(null)
  const latestDraftRef = useRef(draft)
  const loadedRef = useRef(false)
  const previousTaskStatusesRef = useRef<Map<string, ImageGenerationTask['status']>>(new Map())
  const notificationBaselineReadyRef = useRef(false)

  useEffect(() => {
    if (initialMode) setStudioMode(initialMode)
  }, [initialMode])

  useEffect(() => {
    latestDraftRef.current = draft
    loadedRef.current = loaded
  }, [draft, loaded])
  useEffect(() => () => {
    if (!loadedRef.current) return
    if (saveTimerRef.current !== null) window.clearTimeout(saveTimerRef.current)
    void saveImageCenterDraft(draftScope, latestDraftRef.current).catch(() => { /* The page is already unmounted. */ })
  }, [draftScope])

  useEffect(() => {
    let active = true
    void loadImageCenterDraft(draftScope).then((stored) => {
      if (!active || stored?.version !== 1) return
      const defaults = createImageCenterDraft(stored.id, stored.outfits[0]?.id ?? createUuid(), stored.updatedAt)
      setDraft({
        ...stored,
        model: compactImageAssetSet(stored.model),
        outfits: stored.outfits.map((outfit) => ({ ...outfit, ...compactImageAssetSet(outfit) })),
        config: {
          ...defaults.config,
          ...stored.config,
          modes: normalizeImageGenerationModes(stored.config.modes),
          quality: normalizeImageGenerationQuality(stored.config.quality),
          outputFormat: 'png',
        },
        tasks: stored.tasks.map((task) => ({
          ...task,
          status: (task.status as string) === 'waiting_api' ? 'failed' : task.status,
          batchId: task.batchId ?? null,
          clientBatchId: task.clientBatchId ?? null,
          providerTaskId: task.providerTaskId ?? null,
          providerTaskIds: task.providerTaskIds ?? (task.providerTaskId ? [task.providerTaskId] : []),
          modelId: task.modelId ?? (task.provider === 'gpt' ? 'openai/gpt-image-2/edit' : 'google/nano-banana-2/edit'),
          aspectRatio: task.aspectRatio ?? defaults.config.aspectRatio,
          resolution: task.resolution ?? defaults.config.resolution,
          quality: task.quality ?? defaults.config.quality,
          outputFormat: 'png',
          allowBackInference: task.allowBackInference ?? true,
          storyboardShots: task.storyboardShots ?? parseStoryboardPrompt(task.prompt.storyboard),
          error: (task.status as string) === 'waiting_api' ? '此任务创建于 API 接入前，请重新生成。' : task.error,
          errorCode: task.errorCode ?? ((task.status as string) === 'waiting_api' ? 'LEGACY_DRAFT_TASK' : null),
          retryable: task.retryable ?? true,
        })),
      })
    }).catch(() => { if (active) setSaveState('error') }).finally(() => { if (active) setLoaded(true) })
    return () => { active = false }
  }, [draftScope])
  useEffect(() => {
    if (!loaded) return
    if (saveTimerRef.current !== null) window.clearTimeout(saveTimerRef.current)
    saveTimerRef.current = window.setTimeout(() => { void saveImageCenterDraft(draftScope, draft).then(() => setSaveState('saved')).catch(() => setSaveState('error')) }, 450)
    return () => { if (saveTimerRef.current !== null) window.clearTimeout(saveTimerRef.current) }
  }, [draft, draftScope, loaded])
  useEffect(() => {
    const controller = new AbortController()
    let active = true
    void fetch('/api/v1/system/status', { credentials: 'same-origin', cache: 'no-store', signal: controller.signal }).then((response) => {
      if (!active) return
      const maintenance = response.headers.get('x-libtv-maintenance')?.toLowerCase()
      if (maintenance === 'query-only') {
        setGenerationAvailability('unavailable')
        setGenerationAvailabilityReason('当前处于维护模式，仅支持登录和查询已保存任务，生成服务暂未开放。')
      } else if (!response.ok) {
        setGenerationAvailability('unavailable')
        setGenerationAvailabilityReason('当前无法确认生图服务状态，创建任务已暂停，请稍后再试或联系管理员。')
      } else {
        setGenerationAvailability('available')
        setGenerationAvailabilityReason('')
      }
    }).catch(() => {
      if (!active) return
      setGenerationAvailability('unavailable')
      setGenerationAvailabilityReason('当前无法连接生图服务，创建任务已暂停，请稍后再试或联系管理员。')
    })
    return () => {
      active = false
      controller.abort()
    }
  }, [])

  const hasActiveTasks = draft.tasks.some((task) => !TERMINAL_IMAGE_STATUSES.has(task.status))
  useEffect(() => {
    onActiveTasksChange(loaded && hasActiveTasks)
  }, [hasActiveTasks, loaded, onActiveTasksChange])

  useEffect(() => {
    if (!loaded) return
    const nextStatuses = new Map(draft.tasks.map((task) => [task.id, task.status]))
    if (!notificationBaselineReadyRef.current) {
      previousTaskStatusesRef.current = nextStatuses
      notificationBaselineReadyRef.current = true
      return
    }
    const events = draft.tasks.flatMap((task): ImageCenterNotificationEvent[] => {
      const notification = imageTaskNotificationForTransition(previousTaskStatusesRef.current.get(task.id), task)
      return notification ? [{ taskId: task.id, status: task.status, notification }] : []
    })
    previousTaskStatusesRef.current = nextStatuses
    if (events.length) onNotifications(events)
  }, [draft.tasks, loaded, onNotifications])

  const pollingBatchIds = useMemo(() => Array.from(new Set(draft.tasks
    .filter((task) => task.batchId && !TERMINAL_IMAGE_STATUSES.has(task.status))
    .map((task) => task.batchId!))).join('|'), [draft.tasks])
  useEffect(() => {
    if (!pollingBatchIds) return
    const batchIds = pollingBatchIds.split('|')
    const controller = new AbortController()
    let polling = false
    const poll = async () => {
      if (polling) return
      polling = true
      try {
        const batches = await Promise.all(batchIds.map((batchId) => getImageGenerationBatch(batchId, controller.signal)))
        setDraft((current) => ({
          ...current,
          tasks: batches.reduce(mergeBatchIntoTasks, current.tasks),
          updatedAt: new Date().toISOString(),
        }))
      } catch (cause) {
        if (!controller.signal.aborted) setNotice(cause instanceof ApiError ? cause.message : '生图任务状态刷新失败，稍后将自动重试。')
      } finally { polling = false }
    }
    void poll()
    const timer = window.setInterval(() => void poll(), 2500)
    return () => { controller.abort(); window.clearInterval(timer) }
  }, [pollingBatchIds])

  const updateDraft = (updater: (current: ImageCenterDraft) => ImageCenterDraft) => {
    setSaveState('saving')
    setDraft((current) => ({ ...updater(current), updatedAt: new Date().toISOString() }))
  }
  useEffect(() => {
    if (!active || !openTaskId) return
    setDraft((current) => current.activeTab === 'results'
      ? current
      : { ...current, activeTab: 'results', updatedAt: new Date().toISOString() })
    const frame = window.requestAnimationFrame(() => {
      document.getElementById(`image-task-${openTaskId}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    })
    return () => window.cancelAnimationFrame(frame)
  }, [active, openTaskId])
  const summary = useMemo(() => calculateImageTaskSummary(draft), [draft])
  const errors = useMemo(() => validateImageCenterDraft(draft), [draft])
  const generationBlocked = generationAvailability !== 'available'
  const generationStatusMessage = generationAvailability === 'checking'
    ? '正在检查生图服务状态，请稍候。'
    : generationAvailabilityReason
  const selectedIds = useMemo(() => new Set(draft.selectedOutputIds), [draft.selectedOutputIds])
  const previewOutput = previewOutputId
    ? draft.tasks.flatMap((task) => task.outputs).find((output) => output.id === previewOutputId) ?? null
    : null
  const selectedCompareOutputs = draft.selectedOutputIds.slice(0, 2).map((id) => (
    draft.tasks.flatMap((task) => task.outputs).find((output) => output.id === id)
  )).filter((output): output is ImageGenerationOutput => Boolean(output))
  const reviewOutput = reviewOutputId ? draft.tasks.flatMap((task) => task.outputs).find((output) => output.id === reviewOutputId) : null
  const pendingReviewOutputs = useMemo(
    () => draft.tasks.flatMap((task) => task.outputs).filter((output) => output.qualificationStatus === 'PENDING'),
    [draft.tasks],
  )
  const previewSourceImage = (file: File, label: string) => {
    setPreviewOutputId(null)
    setPreviewSource({ file, label })
  }
  useEffect(() => {
    if (!draft.selectedOutputIds.length) setSelectionBarExpanded(false)
  }, [draft.selectedOutputIds.length])
  const activeOutfit = draft.outfits.find((outfit) => outfit.id === activeOutfitId) ?? draft.outfits[0]
  const activeOutfitIndex = Math.max(0, draft.outfits.findIndex((outfit) => outfit.id === activeOutfit.id))
  const errorTarget = errors[0]?.includes('上传') ? '#asset-composer-title' : '#generation-config-title'
  const updateOutfit = (changed: OutfitDraft) => updateDraft((current) => ({ ...current, outfits: current.outfits.map((item) => item.id === changed.id ? changed : item) }))
  const addOutfit = () => {
    if (draft.outfits.length >= MAX_IMAGE_CENTER_OUTFITS) return
    const id = createUuid()
    setActiveOutfitId(id)
    updateDraft((current) => ({ ...current, outfits: [...current.outfits, createOutfit(id, current.outfits.length + 1)] }))
  }
  const removeOutfit = (id: string) => {
    if (draft.outfits.length <= 1) return
    const removedIndex = draft.outfits.findIndex((outfit) => outfit.id === id)
    const nextActive = draft.outfits[removedIndex + 1] ?? draft.outfits[removedIndex - 1]
    if (activeOutfit.id === id) setActiveOutfitId(nextActive?.id ?? '')
    updateDraft((current) => ({ ...current, outfits: current.outfits.filter((item) => item.id !== id) }))
  }
  const updateConfig = (changes: Partial<ImageCenterDraft['config']>) => updateDraft((current) => ({ ...current, config: { ...current.config, ...changes } }))
  const selectMode = (mode: ImageGenerationMode) => updateConfig({ modes: [mode] })
  const submitTaskSet = async (tasks: ImageGenerationTask[], expectedGenerationCount: number) => {
    if (!tasks.length) return
    const clientBatchId = createUuid()
    const identifiedTasks = tasks.map((task) => ({ ...task, clientBatchId }))
    const { manifest, files } = buildImageGenerationBatchRequest({
      clientBatchId,
      name: draft.name,
      expectedGenerationCount,
      tasks: identifiedTasks,
    })

    setSubmitting(true)
    updateDraft((current) => ({ ...current, activeTab: 'results', tasks: [...identifiedTasks, ...current.tasks], selectedOutputIds: [] }))
    await new Promise((resolve) => window.setTimeout(resolve, 0))
    updateDraft((current) => ({ ...current, tasks: current.tasks.map((task) => identifiedTasks.some((item) => item.id === task.id) ? { ...task, status: 'submitting' } : task) }))
    try {
      const batch = await createImageGenerationBatch(manifest, files)
      updateDraft((current) => ({ ...current, tasks: mergeBatchIntoTasks(current.tasks.map((task) => identifiedTasks.some((item) => item.id === task.id) ? { ...task, batchId: batch.id, clientBatchId } : task), batch) }))
      setNotice(`批次已提交，正在处理 ${expectedGenerationCount} 张图片。`)
    } catch (cause) {
      const uncertain = !(cause instanceof ApiError) || cause.code === 'REQUEST_TIMEOUT' || cause.code === 'WRITE_UNCERTAIN'
      const message = cause instanceof ApiError ? cause.message : '提交结果未知，请勿重复提交；稍后由管理员核对远端记录。'
      if (isGenerationUnavailableError(cause)) {
        setGenerationAvailability('unavailable')
        setGenerationAvailabilityReason(generationUnavailableMessage(cause))
      }
      updateDraft((current) => ({ ...current, tasks: current.tasks.map((task) => identifiedTasks.some((item) => item.id === task.id) ? {
        ...task,
        clientBatchId,
        status: uncertain ? 'write_uncertain' : 'failed',
        error: message,
        errorCode: cause instanceof ApiError ? cause.code : 'WRITE_UNCERTAIN',
        retryable: uncertain ? false : cause instanceof ApiError ? cause.retryable : false,
        errorDetails: cause instanceof ApiError ? cause.details : null,
      } : task) }))
      setNotice(message)
    } finally { setSubmitting(false) }
  }
  const submit = () => {
    if (generationBlocked) {
      setNotice(generationStatusMessage)
      return
    }
    if (errors.length) { setNotice(errors[0]); return }
    const tasks = buildWaitingTasks(draft, createUuid)
    void submitTaskSet(tasks, summary.totalImages)
  }
  const prepareRegeneration = (source: ImageGenerationTask) => {
    if (source.status === 'write_uncertain') {
      setNotice('该批次提交结果未知，请先执行安全查询或联系管理员；不能直接重新生成。')
      return
    }
    const outfitId = createUuid()
    setActiveOutfitId(outfitId)
    updateDraft((current) => createImageCenterRegenerationDraft(current, source, outfitId))
    setNotice(`已载入「${source.outfitName}」的素材与生成配置。`)
    window.requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: 'smooth' }))
  }
  const recoverUncertainTask = async (task: ImageGenerationTask) => {
    if (task.status !== 'write_uncertain') return
    if (!task.clientBatchId) {
      setNotice('该批次缺少安全查询身份，请联系管理员核对；请勿重新生成。')
      return
    }
    try {
      const recovery = await querySubmissionRecovery({
        kind: 'image',
        clientId: task.clientBatchId,
        idempotencyKey: task.clientBatchId,
      })
      if (recovery.state === 'submitted' && recovery.resourceId) {
        const batch = await getImageGenerationBatch(recovery.resourceId)
        updateDraft((current) => ({
          ...current,
          tasks: mergeBatchIntoTasks(current.tasks, batch),
          updatedAt: new Date().toISOString(),
        }))
        setNotice('已恢复服务端批次记录，正在继续读取原任务状态；未创建新任务。')
        return
      }
      if (recovery.state === 'in_progress') {
        setNotice('服务端仍在处理原提交，请稍后再次查询；未创建新任务。')
        return
      }
      setNotice(recovery.state === 'unknown'
        ? '服务端记录存在歧义，已标记为需要管理员核对；请勿重新生成。'
        : '暂未找到原批次记录，不能据此判断未扣费；请联系管理员核对。')
    } catch (cause) {
      setNotice(cause instanceof ApiError ? cause.message : '安全查询失败，请稍后重试；请勿重新生成。')
    }
  }
  const updateOutputQuality = (id: string, values: Partial<ImageGenerationOutput>) => {
    updateDraft((current) => ({
      ...current,
      tasks: current.tasks.map((task) => ({
        ...task,
        outputs: task.outputs.map((output) => output.id === id ? { ...output, ...values } : output),
      })),
    }))
  }
  const toggleOutput = (id: string) => {
    const owner = draft.tasks.find((task) => task.outputs.some((output) => output.id === id))
    const output = owner?.outputs.find((item) => item.id === id)
    if (!owner || !output) return
    const alreadySelected = selectedIds.has(id)
    const selectedFromOwner = owner?.outputs.filter((output) => selectedIds.has(output.id)).length ?? 0
    if (!alreadySelected && selectedFromOwner >= 6) { setNotice('每套视频最多选择 6 张分镜，另保留 1 个主体引用名额。'); return }
    updateDraft((current) => ({ ...current, selectedOutputIds: current.selectedOutputIds.includes(id) ? current.selectedOutputIds.filter((item) => item !== id) : [...current.selectedOutputIds, id] }))
  }
  const rejectOutput = (id: string) => setReviewOutputId(id)
  const placeOutput = (taskId: string, outputId: string, beforeOutputId?: string) => {
    const owner = draft.tasks.find((task) => task.id === taskId && task.outputs.some((output) => output.id === outputId))
    if (!owner) return
    const alreadySelected = selectedIds.has(outputId)
    const selectedFromOwner = owner.outputs.filter((output) => selectedIds.has(output.id)).length
    if (!alreadySelected && selectedFromOwner >= 6) { setNotice('每套视频最多选择 6 张分镜，另保留 1 个主体引用名额。'); return }
    updateDraft((current) => {
      const nextIds = current.selectedOutputIds.filter((id) => id !== outputId)
      const targetIndex = beforeOutputId ? nextIds.indexOf(beforeOutputId) : -1
      if (targetIndex >= 0) nextIds.splice(targetIndex, 0, outputId)
      else {
        const currentOwner = current.tasks.find((task) => task.id === taskId)
        const ownerIds = new Set(currentOwner?.outputs.map((output) => output.id) ?? [])
        let insertionIndex = nextIds.length
        for (let index = nextIds.length - 1; index >= 0; index -= 1) {
          if (ownerIds.has(nextIds[index])) { insertionIndex = index + 1; break }
        }
        nextIds.splice(insertionIndex, 0, outputId)
      }
      return { ...current, selectedOutputIds: nextIds }
    })
  }
  const prepareVideos = async () => {
    if (preparingVideos) return
    const selectedTasks = getOrderedSelectedTasks(draft.tasks, draft.selectedOutputIds)
    if (!selectedTasks.length) return
    if (selectedTasks.some(({ outputs }) => outputs.some((output) => output.qualificationStatus !== 'QUALIFIED'))) {
      setNotice('只有已完成人工审核并标记为合格的图片才能进入视频生成。')
      return
    }
    const preparedOutputIds = new Set(selectedTasks.flatMap(({ outputs }) => outputs.map((output) => output.id)))
    setPreparingVideos(true)
    try {
      await onPrepareVideos(
        selectedTasks.map(({ task, outputs }) => ({ task, outputs, subjectSource: 'product-front' })),
        () => updateDraft((current) => ({
          ...current,
          selectedOutputIds: current.selectedOutputIds.filter((id) => !preparedOutputIds.has(id)),
        })),
      )
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : '无法准备视频制作素材。')
    } finally { setPreparingVideos(false) }
  }
  if (!loaded) return <div className="image-center-loading" hidden={!active}><LoaderCircle className="spin" size={24} /><strong>正在恢复图片批次</strong></div>

  return <div className="image-center page-view" hidden={!active}>
    <header className="image-center-title"><div><span>{studioMode === 'director' ? '图片生产与导演规划' : '批量换装工作台'}</span><h1>图片中心</h1><p>{studioMode === 'director' ? '从真实商品输入开始，整理创意方向与生产包。' : '一个模特对应多套产品，集中完成生图、挑图和视频衔接。'}</p></div><div className="image-center-title__actions"><span className={`image-center-save-state is-${saveState}`}><Save size={14} />{saveState === 'saved' ? '草稿已保存' : saveState === 'saving' ? '正在保存' : '草稿保存失败'}</span></div></header>
    <nav className="image-center-tabs" aria-label="图片中心模式"><button type="button" className={studioMode === 'custom' && draft.activeTab === 'create' ? 'is-active' : ''} onClick={() => { setStudioMode('custom'); updateDraft((current) => ({ ...current, activeTab: 'create' })) }}><Layers3 size={17} />批量创作</button><button type="button" className={studioMode === 'custom' && draft.activeTab === 'results' ? 'is-active' : ''} onClick={() => { setStudioMode('custom'); updateDraft((current) => ({ ...current, activeTab: 'results' })) }}><Images size={17} />生图记录{draft.tasks.length ? <i>{draft.tasks.length}</i> : null}</button><button type="button" className={studioMode === 'director' ? 'is-active' : ''} onClick={() => setStudioMode('director')}><WandSparkles size={17} />智能导演</button></nav>
    {notice ? <div className={`image-center-notice${errors.includes(notice) ? ' is-danger' : ''}`} role="status"><AlertTriangle size={16} /><span>{notice}</span><button type="button" onClick={() => setNotice('')} aria-label="关闭提示"><X size={15} /></button></div> : null}

    {studioMode === 'director' ? <DirectorStudio /> : null}
    {studioMode === 'custom' && draft.activeTab === 'create' ? <div className="image-center-create">
      <section className="image-center-section asset-composer" aria-labelledby="asset-composer-title">
        <div className="image-center-section__heading"><div><span className="section-number">01</span><div><h2 id="asset-composer-title">素材编排</h2><p>左侧模特复用到全部套装，右侧每套产品独立生成。</p></div></div><div className="asset-composer-toolbar"><span className="section-state"><Shirt size={15} />{summary.outfitCount}/{draft.outfits.length} 套已就绪</span><a className="image-center-jump" href="#generation-config-title"><WandSparkles size={15} />生成配置</a></div></div>
        <div className="asset-composer-grid">
          <aside className="model-pack-column">
            <div className="asset-pack-heading"><span><UserRound size={18} /></span><div><h3>本批次模特</h3><p>正面必填，背面和侧面可选</p></div><i className={draft.model.front ? 'is-ready' : ''}>{draft.model.front ? '已就绪' : '待上传'}</i></div>
            <OrderedAssetUpload idPrefix="image-center-model" title="模特图片" description="图一固定为人物与环境；背面、侧面为补充参考" assets={draft.model} onChange={(model) => updateDraft((current) => ({ ...current, model }))} />
          </aside>
          <div className="outfit-pack-column" aria-labelledby="outfits-title">
            <div className="asset-pack-heading"><span><Package size={18} /></span><div><h3 id="outfits-title">产品套装</h3><p>每套正面必填，背面和侧面可选</p></div><div className="outfits-heading-actions"><strong>{draft.outfits.length}/{MAX_IMAGE_CENTER_OUTFITS}</strong><button type="button" className="primary-button outfit-add-button" disabled={draft.outfits.length >= MAX_IMAGE_CENTER_OUTFITS} onClick={addOutfit}><Plus size={16} />添加套装</button></div></div>
            <div className="outfit-workspace">
              <div className="outfit-navigator">
                <div className="outfit-navigator__head"><strong>套装列表</strong><span>{summary.outfitCount} 套已就绪</span></div>
                <div className="outfit-nav-list" role="tablist" aria-label="产品套装列表">{draft.outfits.map((outfit, index) => <OutfitNavItem key={outfit.id} outfit={outfit} index={index} selected={outfit.id === activeOutfit.id} canRemove={draft.outfits.length > 1} onSelect={() => setActiveOutfitId(outfit.id)} onRemove={() => removeOutfit(outfit.id)} />)}</div>
                {draft.outfits.length < MAX_IMAGE_CENTER_OUTFITS ? <button type="button" className="outfit-nav-add" onClick={addOutfit}><Plus size={15} />添加下一套</button> : null}
              </div>
              <div id="active-outfit-editor" className="active-outfit-editor" role="tabpanel" aria-labelledby={`outfit-tab-${activeOutfit.id}`}>
                <OutfitCard outfit={activeOutfit} index={activeOutfitIndex} onChange={updateOutfit} />
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="image-center-section generation-config" aria-labelledby="generation-config-title">
        <div className="image-center-section__heading"><div><span className="section-number">02</span><div><h2 id="generation-config-title">生成配置</h2><p>统一配置会应用到全部已就绪套装。</p></div></div><span className="section-state"><WandSparkles size={15} />预计 {summary.totalImages} 张</span></div>
        <div className="image-config-grid">
          <fieldset className="image-config-block"><legend>生成引擎</legend><div className="image-provider-control">{(['gpt', 'nanobanana'] as ImageProvider[]).map((provider) => <button key={provider} type="button" className={draft.config.provider === provider ? 'is-selected' : ''} onClick={() => updateConfig({ provider })}><span>{provider === 'gpt' ? 'GPT Image 2' : 'Nano Banana 2'}</span><small>WaveSpeed API</small>{draft.config.provider === provider ? <Check size={14} /> : null}</button>)}</div></fieldset>
          <fieldset className="image-config-block image-config-select"><legend>画面比例</legend><select aria-label="画面比例" value={draft.config.aspectRatio} onChange={(event) => updateConfig({ aspectRatio: event.target.value })}><option value="9:16">9:16</option><option value="16:9">16:9</option><option value="1:1">1:1</option><option value="3:4">3:4</option><option value="4:3">4:3</option></select></fieldset>
          <fieldset className="image-config-block image-config-select"><legend>分辨率</legend><select aria-label="分辨率" value={draft.config.resolution} onChange={(event) => updateConfig({ resolution: event.target.value })}><option value="1k">1K</option><option value="2k">2K</option><option value="4k">4K</option></select></fieldset>
          <fieldset className="image-config-block"><legend>统一结果数量</legend><div className="image-result-count">{([1, 2, 3, 4] as const).map((count) => <button key={count} type="button" className={draft.config.resultCount === count ? 'is-selected' : ''} onClick={() => updateConfig({ resultCount: count })}>{count}</button>)}</div></fieldset>
        </div>
        <div className="image-prompt-grid" role="radiogroup" aria-label="生成任务">
          <section className={draft.config.modes.includes('fusion') ? 'is-selected' : 'is-disabled'}><header><button type="button" className="image-prompt-mode" role="radio" aria-checked={draft.config.modes.includes('fusion')} onClick={() => selectMode('fusion')}><span><Sparkles size={17} /></span><span><strong>多图融合</strong><small>按现有视角生成换装基准图</small></span><i>{draft.config.modes.includes('fusion') ? <Check size={14} /> : null}</i></button></header><CustomPromptField scope="image_fusion" label="自定义提示词" value={draft.config.fusionPrompt} disabled={!draft.config.modes.includes('fusion')} onChange={(fusionPrompt) => updateConfig({ fusionPrompt })} placeholder="描述人物一致性、服装还原和画面要求" /></section>
          <section className={draft.config.modes.includes('storyboard') ? 'is-selected' : 'is-disabled'}><header><button type="button" className="image-prompt-mode" role="radio" aria-checked={draft.config.modes.includes('storyboard')} onClick={() => selectMode('storyboard')}><span><Images size={17} /></span><span><strong>分镜图生成</strong><small>从一段提示词扩展有序镜头</small></span><i>{draft.config.modes.includes('storyboard') ? <Check size={14} /> : null}</i></button></header><CustomPromptField scope="image_storyboard" label="自定义提示词" value={draft.config.storyboardPrompt} disabled={!draft.config.modes.includes('storyboard')} onChange={(storyboardPrompt) => updateConfig({ storyboardPrompt })} placeholder="用一整段文字描述镜头顺序和展示重点" /></section>
        </div>
        <label className="back-inference-toggle"><input type="checkbox" checked={draft.config.allowBackInference} onChange={(event) => updateConfig({ allowBackInference: event.target.checked })} /><span><i>{draft.config.allowBackInference ? <Check size={13} /> : null}</i><strong>允许推测缺失的背面</strong><small>只有模特或产品一方提供背面时继续生成，并给结果添加风险标签。</small></span></label>
        <div className="image-generation-summary"><div><span><Shirt size={18} /></span><p><strong>{summary.outfitCount}</strong><small>就绪套装</small></p></div><div><span><Sparkles size={18} /></span><p><strong>{summary.fusionImages}</strong><small>融合结果</small></p></div><div><span><Images size={18} /></span><p><strong>{summary.storyboardImages}</strong><small>分镜结果</small></p></div><div className="is-total"><span><WandSparkles size={18} /></span><p><strong>{summary.totalImages}</strong><small>预计总图片</small></p></div><div className="image-generation-submit"><small>{summary.inferredBackOutfitCount ? `${summary.inferredBackOutfitCount} 套将推测背面` : '不会强制要求背面或侧面图'}</small><p className="image-generation-submit__hint" role="status">{generationStatusMessage}</p></div></div>
        {errors.length ? <div className="image-config-errors" role="alert"><AlertTriangle size={16} /><span>{errors[0]}</span></div> : null}
      </section>
    </div> : studioMode === 'custom' ? <section className="image-results" aria-labelledby="image-results-title">
      <div className="image-results-heading"><div><h2 id="image-results-title">生图记录</h2><p>当前浏览器已提交的任务会显示在这里，可查看进度、历史结果并直接挑选分镜。</p></div><div className="image-results-heading__actions">{selectedCompareOutputs.length === 2 ? <button type="button" className="secondary-button" onClick={() => setCompareOpen(true)}><Columns2 size={16} />并排比较</button> : null}{pendingReviewOutputs.length ? <button type="button" className="secondary-button" onClick={() => setBatchReviewOpen(true)}><CheckCircle2 size={16} />批量审核<span className="image-review-count">{pendingReviewOutputs.length}</span></button> : null}<button type="button" className="secondary-button" onClick={() => updateDraft((current) => ({ ...current, activeTab: 'create' }))}><Plus size={16} />继续创建</button></div></div>
      {draft.tasks.filter((task) => task.status === 'write_uncertain').map((task) => <div className="image-center-notice is-danger" key={`recovery-${task.id}`} role="status"><AlertTriangle size={16} /><span>{task.outfitName} 的提交结果未知，请先查询服务端原批次。</span><button type="button" className="secondary-button" onClick={() => void recoverUncertainTask(task)}><RotateCcw size={15} />安全查询</button></div>)}
      {!draft.tasks.length ? <div className="image-results-empty"><span><Images size={28} /></span><h3>还没有生图记录</h3><p>提交第一组生图任务后，可在这里查看任务进度和生成结果。</p><button type="button" className="primary-button" onClick={() => updateDraft((current) => ({ ...current, activeTab: 'create' }))}>开始配置</button></div> : <div className="image-task-list">{draft.tasks.map((task) => {
        const status = imageStatusPresentation(task.status)
        const active = ['uploading', 'submitting', 'queued', 'running'].includes(task.status)
        return <article id={`image-task-${task.id}`} key={task.id} className="image-task-card"><header><div className="image-task-title"><span><Package size={18} /></span><div><strong>{task.outfitName}</strong><small>{task.sku || new Date(task.createdAt).toLocaleString('zh-CN')}</small></div></div><div className="image-task-header-actions"><div className="image-task-meta"><span>{task.provider === 'gpt' ? 'GPT Image 2' : 'Nano Banana 2'}</span><span>{task.modes.map((mode) => mode === 'fusion' ? '多图融合' : '分镜图').join(' + ')}</span><i className={`is-${status.tone}`}>{active ? <LoaderCircle className="spin" size={13} /> : task.status === 'completed' ? <CheckCircle2 size={13} /> : <Clock3 size={13} />}{status.label}</i></div><button type="button" className="secondary-button image-task-regenerate" onClick={() => prepareRegeneration(task)} title="使用相同素材和配置重新创作"><RotateCcw size={15} />重新生成</button></div></header><div className="image-task-body"><div className="image-task-sources"><SourceThumb file={task.model.front} label="模特正面" onPreview={previewSourceImage} /><SourceThumb file={task.product.front} label="产品正面" onPreview={previewSourceImage} /><SourceThumb file={task.model.back} label="模特背面" onPreview={previewSourceImage} /><SourceThumb file={task.product.back} label="产品背面" onPreview={previewSourceImage} /><SourceThumb file={task.model.side} label="模特侧面" onPreview={previewSourceImage} /><SourceThumb file={task.product.side} label="产品侧面" onPreview={previewSourceImage} /></div>{task.outputs.length ? <div className="image-output-grid">{task.outputs.map((output) => <OutputCard key={output.id} taskId={task.id} output={output} selected={selectedIds.has(output.id)} onToggle={() => void toggleOutput(output.id)} onReject={() => void rejectOutput(output.id)} onPreview={() => { setPreviewSource(null); setPreviewOutputId(output.id) }} />)}</div> : <div className={`image-task-waiting${task.error ? ' is-error' : ''}`}><span>{active ? <LoaderCircle className="spin" size={20} /> : <Clock3 size={20} />}</span><div><strong>{task.error ? `${task.errorCode ?? 'GENERATION_FAILED'} · ${task.error}` : status.label}</strong><p>{task.error ? (task.retryable === false ? '该错误不能安全自动重试，请先核对远端任务或联系管理员。' : '可以检查配置后重新提交此套装。') : task.status === 'queued' ? '任务已进入 WaveSpeed 队列。' : task.status === 'running' ? 'WaveSpeed 正在生成图片，页面会自动刷新结果。' : '正在上传参考图并创建远端任务。'}</p></div></div>}</div><details className="image-task-technical"><summary>技术信息<ChevronRight size={14} /></summary><dl><dt>Task ID</dt><dd>{task.id}</dd><dt>Batch ID</dt><dd>{task.batchId ?? '尚未分配'}</dd><dt>Remote Task IDs</dt><dd>{task.providerTaskIds.length ? task.providerTaskIds.join(', ') : '尚未分配'}</dd><dt>Model ID</dt><dd>{task.modelId}</dd>{task.errorCode ? <><dt>错误代码</dt><dd>{task.errorCode}</dd></> : null}</dl></details></article>
      })}</div>}
    </section> : null}
    {active && studioMode === 'custom' && draft.activeTab === 'create' ? createPortal(<div className="image-center-command-bar">
      <div><strong>{summary.outfitCount}/{draft.outfits.length} 套已就绪</strong><span>预计生成 {summary.totalImages} 张图片</span></div>
      {errors.length ? <a href={errorTarget}><AlertTriangle size={15} />{errors[0]}</a> : generationBlocked ? <span id="image-generation-availability" title={generationStatusMessage}><AlertTriangle size={15} />{generationStatusMessage}</span> : <span id="image-generation-availability" className="is-ready"><CheckCircle2 size={15} />配置完整</span>}
      <button type="button" className="primary-button" disabled={submitting || generationBlocked} onClick={submit} title={generationBlocked ? generationStatusMessage : undefined} aria-describedby="image-generation-availability">{submitting ? <LoaderCircle className="spin" size={17} /> : <WandSparkles size={17} />}{submitting ? '正在提交' : generationBlocked ? '生成暂不可用' : '创建生图任务'}</button>
    </div>, document.body) : null}
    {active && studioMode === 'custom' && draft.activeTab === 'results' && selectedIds.size ? createPortal(<SelectionWorkbench
      tasks={draft.tasks}
      selectedOutputIds={draft.selectedOutputIds}
      expanded={selectionBarExpanded}
      preparing={preparingVideos}
      onExpandedChange={setSelectionBarExpanded}
      onClear={() => updateDraft((current) => ({ ...current, selectedOutputIds: [] }))}
      onRemove={(outputId) => updateDraft((current) => ({ ...current, selectedOutputIds: current.selectedOutputIds.filter((id) => id !== outputId) }))}
      onPlaceOutput={placeOutput}
      onGenerate={() => void prepareVideos()}
    />, document.body) : null}
    {active && reviewOutput ? <ImageOutputReview key={reviewOutput.id} output={reviewOutput} onClose={() => setReviewOutputId(null)} onSaved={(values) => {
      updateOutputQuality(reviewOutput.id, values)
      if (values.qualificationStatus === 'REJECTED') updateDraft((current) => ({ ...current, selectedOutputIds: current.selectedOutputIds.filter((id) => id !== reviewOutput.id) }))
    }} /> : null}
    {active && batchReviewOpen ? <BatchImageOutputReview
      outputs={pendingReviewOutputs}
      onClose={() => setBatchReviewOpen(false)}
      onSaved={(outputId, values) => {
        updateOutputQuality(outputId, values)
        if (values.qualificationStatus === 'REJECTED') updateDraft((current) => ({ ...current, selectedOutputIds: current.selectedOutputIds.filter((id) => id !== outputId) }))
      }}
    /> : null}
    {active && previewOutput ? <OutputPreview
      output={previewOutput}
      selected={selectedIds.has(previewOutput.id)}
      onToggle={() => toggleOutput(previewOutput.id)}
      onClose={() => setPreviewOutputId(null)}
    /> : null}
    {active && previewSource ? <AssetPreviewDialog
      file={previewSource.file}
      label={previewSource.label}
      onClose={() => setPreviewSource(null)}
    /> : null}
    {active && compareOpen ? <ImageOutputCompare outputs={selectedCompareOutputs} onClose={() => setCompareOpen(false)} /> : null}
  </div>
}
