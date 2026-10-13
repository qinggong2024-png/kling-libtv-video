import { Check, CheckCircle2, ChevronDown, ChevronUp, Download, Film, GripVertical, LoaderCircle, Plus, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { DragEvent } from 'react'
import { createPortal } from 'react-dom'
import { ApiError, saveAsset, setImageOutputQualityDecision } from '../../api'
import { getOrderedSelectedTasks } from '../../imageCenterModel'
import type { ImageGenerationOutput, ImageGenerationTask } from '../../imageCenterModel'
import { FoundationDrawer } from '../../shared/components/ui'
import { HumanReviewPanel } from '../human-review/HumanReviewPanel'
import { AssetPreview, AuthenticatedAssetPreview } from './shared/ImageAssets'
const IMAGE_OUTPUT_DRAG_TYPE = 'application/x-image-center-output'

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

export function AssetPreviewDialog({ file, url = '', label, selection, onClose }: {
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
    <HumanReviewPanel subjectType="IMAGE_OUTPUT" subjectId={output.id} />
    {error ? <p role="alert" className="notice">{error}</p> : null}
  </FoundationDrawer>
}

export function OutputPreview({ output, selected, onToggle, onClose }: {
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

export function SelectionWorkbench({ tasks, selectedOutputIds, expanded, preparing, onExpandedChange, onClear, onRemove, onPlaceOutput, onGenerate }: {
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

