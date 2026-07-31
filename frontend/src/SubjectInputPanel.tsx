import {
  AlertTriangle,
  History,
  LoaderCircle,
  PackageOpen,
  X,
} from 'lucide-react'
import { useEffect, useId, useState } from 'react'
import type { ChangeEvent } from 'react'

import {
  KLING_MAX_REFERENCES,
  SUBJECT_IMAGE_ACCEPT,
  SUBJECT_MAX_DETAIL_IMAGES,
  createEmptySubjectReferenceFiles,
  getSubjectFileCount,
  getSubjectReferenceCount,
  validateReferenceBudget,
  validateSubjectReferenceFiles,
} from './subjectFiles'
import type { SubjectInputMode, SubjectReferenceFiles } from './subjectFiles'
import { fillSubjectDropSlots, isSubjectPanelDropExcluded } from './subjectPanelDrop'
import { getKlingElementStatusLabel, isKlingElementAvailable } from './klingElementStatus'
import { swapSubjectReferenceFiles } from './subjectUploadReorder'
import type { SubjectDragSlot } from './subjectUploadReorder'
import type { KlingElement } from './types'

const COLLAPSED_HISTORY_COUNT = 6
const SUBJECT_DRAG_MIME = 'application/x-subject-slot'

function readSubjectDragSlot(dataTransfer: DataTransfer): SubjectDragSlot | null {
  const value = dataTransfer.getData(SUBJECT_DRAG_MIME) || dataTransfer.getData('text/plain')
  if (!value) return null
  try {
    const parsed = JSON.parse(value) as SubjectDragSlot
    if (!parsed || !['frontalImage', 'backImage', 'detailImages'].includes(parsed.slot)) return null
    return parsed
  } catch {
    return null
  }
}

export type SubjectHistoryElement = Pick<
  KlingElement,
  'id' | 'name' | 'description' | 'status' | 'imageUrls' | 'raw'
>

export interface SubjectInputPanelProps {
  mode: SubjectInputMode
  onModeChange: (mode: SubjectInputMode) => void
  uploadedFiles: SubjectReferenceFiles
  onUploadedFilesChange: (files: SubjectReferenceFiles) => void
  elements: readonly SubjectHistoryElement[]
  selectedElementId: string
  onSelectedElementIdChange: (elementId: string) => void
  storyboardReferenceCount: number
  referenceLimit?: number
  disabled?: boolean
  elementsLoading?: boolean
  error?: string | null
  elementsError?: string | null
  className?: string
}

function isUsableElement(element: SubjectHistoryElement): boolean {
  return !element.raw?.localJob && isKlingElementAvailable(element.status)
}

function LocalFileThumbnail({ file, alt }: { file: File; alt: string }) {
  const [preview, setPreview] = useState<{ file: File; src: string } | null>(null)

  useEffect(() => {
    let active = true
    const objectUrl = URL.createObjectURL(file)
    queueMicrotask(() => {
      if (active) setPreview({ file, src: objectUrl })
    })
    return () => {
      active = false
      URL.revokeObjectURL(objectUrl)
    }
  }, [file])

  return preview?.file === file
    ? <img src={preview.src} alt={alt} draggable={false} />
    : <span className="image-skeleton" aria-label="图片加载中" />
}

function UploadTile({
  id,
  label,
  required,
  file,
  disabled,
  invalid,
  onChange,
  onDrop,
  dragSource,
  onInternalDrop,
  onRemove,
}: {
  id: string
  label: string
  required?: boolean
  file: File | null
  disabled: boolean
  invalid?: boolean
  onChange: (event: ChangeEvent<HTMLInputElement>) => void
  onDrop: (files: File[]) => void
  dragSource: SubjectDragSlot
  onInternalDrop: (source: SubjectDragSlot) => void
  onRemove: () => void
}) {
  return <div className={`subject-upload-tile${file ? ' is-filled' : ''}${required ? ' is-required' : ''}`}>
    <label
      className="subject-upload-tile__dropzone"
      htmlFor={id}
      onDragOver={(event) => {
        event.preventDefault()
        event.stopPropagation()
        event.dataTransfer.dropEffect = Array.from(event.dataTransfer.types).includes(SUBJECT_DRAG_MIME) ? 'move' : 'copy'
      }}
      onDrop={(event) => {
        event.preventDefault()
        event.stopPropagation()
        if (disabled) return
        const source = readSubjectDragSlot(event.dataTransfer)
        if (source) onInternalDrop(source)
        else onDrop(Array.from(event.dataTransfer.files))
      }}
    >
      {file ? <span
        className="subject-upload-tile__preview"
        role="img"
        aria-label={`${label}预览：${file.name}`}
        draggable={!disabled}
        title="Drag to swap positions"
        onDragStart={(event) => {
          event.stopPropagation()
          event.dataTransfer.effectAllowed = 'move'
          event.dataTransfer.setData(SUBJECT_DRAG_MIME, JSON.stringify(dragSource))
          event.dataTransfer.setData('text/plain', JSON.stringify(dragSource))
        }}
      >
        <LocalFileThumbnail file={file} alt="" />
      </span> : null}
      {!file ? <span className="subject-upload-tile__copy">
        <strong>{label}</strong>
        <span>拖拽或选择</span>
      </span> : null}
    </label>
    {file ? <button
        type="button"
        className="subject-upload-tile__remove"
        disabled={disabled}
        onClick={onRemove}
        aria-label={`移除${label}“${file.name}”`}
      >
        <X aria-hidden="true" size={15} />
      </button> : null}
    <input
      id={id}
      className="sr-only"
      type="file"
      accept={SUBJECT_IMAGE_ACCEPT}
      disabled={disabled}
      aria-invalid={invalid || undefined}
      onChange={onChange}
    />
  </div>
}

function DetailUploadTile({
  id,
  files,
  disabled,
  invalid,
  onChange,
  onDrop,
  onInternalDrop,
  onRemove,
}: {
  id: string
  files: File[]
  disabled: boolean
  invalid?: boolean
  onChange: (event: ChangeEvent<HTMLInputElement>) => void
  onDrop: (files: File[]) => void
  onInternalDrop: (source: SubjectDragSlot, targetIndex?: number) => void
  onRemove: (index: number) => void
}) {
  const isFull = files.length >= SUBJECT_MAX_DETAIL_IMAGES
  return <div className={`subject-upload-tile subject-upload-tile--details${files.length ? ' is-filled' : ''}`}>
    <label
      className="subject-upload-tile__dropzone"
      htmlFor={id}
      onDragOver={(event) => {
        event.preventDefault()
        event.stopPropagation()
        event.dataTransfer.dropEffect = Array.from(event.dataTransfer.types).includes(SUBJECT_DRAG_MIME) ? 'move' : 'copy'
      }}
      onDrop={(event) => {
        event.preventDefault()
        event.stopPropagation()
        if (disabled) return
        const source = readSubjectDragSlot(event.dataTransfer)
        if (source) {
          const target = (event.target as Element | null)?.closest<HTMLElement>('[data-subject-detail-index]')
          const targetIndex = target?.dataset.subjectDetailIndex
          onInternalDrop(source, targetIndex === undefined ? undefined : Number(targetIndex))
        } else if (!isFull) onDrop(Array.from(event.dataTransfer.files))
      }}
    >
      {files.length ? <span className={`subject-upload-tile__previews subject-upload-tile__previews--${files.length}`}>
        {files.map((file, index) => <span
          key={`${file.name}-${file.size}-${file.lastModified}`}
          className="subject-upload-tile__preview"
          role="img"
          data-subject-detail-index={index}
          draggable={!disabled}
          title="Drag to swap positions"
          onDragStart={(event) => {
            event.stopPropagation()
            event.dataTransfer.effectAllowed = 'move'
            const source: SubjectDragSlot = { slot: 'detailImages', index }
            event.dataTransfer.setData(SUBJECT_DRAG_MIME, JSON.stringify(source))
            event.dataTransfer.setData('text/plain', JSON.stringify(source))
          }}
          aria-label={`侧面图预览：${file.name}`}
        >
          <LocalFileThumbnail file={file} alt="" />
        </span>)}
      </span> : null}
      {!files.length ? <span className="subject-upload-tile__copy">
        <strong>侧面图</strong>
        <span>拖拽或选择</span>
      </span> : null}
    </label>
    {files.map((file, index) => <button
      key={`${file.name}-${file.size}-${file.lastModified}`}
      type="button"
      className={`subject-upload-tile__remove${files.length > 1 ? ` subject-upload-tile__remove--detail-${index}` : ''}`}
      disabled={disabled}
      onClick={() => onRemove(index)}
      aria-label={`移除侧面图“${file.name}”`}
    >
      <X aria-hidden="true" size={15} />
    </button>)}
    <input
      id={id}
      className="sr-only"
      type="file"
      multiple
      accept={SUBJECT_IMAGE_ACCEPT}
      disabled={disabled || isFull}
      aria-invalid={invalid || undefined}
      onChange={onChange}
    />
  </div>
}

export function SubjectInputPanel({
  mode,
  onModeChange,
  uploadedFiles,
  onUploadedFilesChange,
  elements,
  selectedElementId,
  onSelectedElementIdChange,
  storyboardReferenceCount,
  referenceLimit = KLING_MAX_REFERENCES,
  disabled = false,
  elementsLoading = false,
  error = null,
  elementsError = null,
  className = '',
}: SubjectInputPanelProps) {
  const id = useId()
  const [selectionError, setSelectionError] = useState('')
  const [showAllHistory, setShowAllHistory] = useState(false)
  const validation = validateSubjectReferenceFiles(uploadedFiles)
  const subjectReferenceCount = getSubjectReferenceCount(mode, uploadedFiles, selectedElementId)
  const budget = validateReferenceBudget(storyboardReferenceCount, subjectReferenceCount, referenceLimit)
  const selectedElement = elements.find((element) => element.id === selectedElementId)
  const usableElements = elements.filter(isUsableElement)
  const visibleElements = showAllHistory
    ? usableElements
    : usableElements.slice(0, COLLAPSED_HISTORY_COUNT)
  const historySelectionError = mode === 'history' && selectedElementId
    ? !selectedElement
      ? '所选历史主体已不可用，请重新选择。'
      : !isUsableElement(selectedElement)
        ? `“${selectedElement.name || selectedElement.id}”当前${getKlingElementStatusLabel(selectedElement.status)}，暂不能用于生成。`
        : ''
    : ''
  const panelErrors = [
    selectionError,
    error ?? '',
    budget.error,
    historySelectionError,
  ].filter(Boolean)
  const uploadHasFiles = getSubjectFileCount(uploadedFiles) > 0
  const shouldAlignUploadedMedia = mode === 'upload' && storyboardReferenceCount > 0 && uploadHasFiles
  const panelClassName = [
    'subject-input-panel',
    shouldAlignUploadedMedia ? 'subject-input-panel--align-uploaded-media' : '',
    className,
  ].filter(Boolean).join(' ')

  const clearUploadedFiles = () => {
    if (uploadHasFiles) onUploadedFilesChange(createEmptySubjectReferenceFiles())
  }

  const changeMode = (nextMode: SubjectInputMode) => {
    if (disabled || nextMode === mode) return
    setSelectionError('')
    setShowAllHistory(false)
    if (nextMode !== 'upload') clearUploadedFiles()
    if (nextMode !== 'history' && selectedElementId) onSelectedElementIdChange('')
    onModeChange(nextMode)
  }

  const clearSubject = () => {
    if (disabled) return
    setSelectionError('')
    setShowAllHistory(false)
    clearUploadedFiles()
    if (selectedElementId) onSelectedElementIdChange('')
    if (mode !== 'none') onModeChange('none')
  }

  const selectSingleFile = (field: 'frontalImage' | 'backImage', file: File | null) => {
    if (!file) return
    if (mode !== 'upload') changeMode('upload')
    setSelectionError('')
    onUploadedFilesChange({ ...uploadedFiles, [field]: file })
  }

  const selectDetailFiles = (chosen: File[]) => {
    if (!chosen.length) return
    if (mode !== 'upload') changeMode('upload')
    const availableSlots = SUBJECT_MAX_DETAIL_IMAGES - uploadedFiles.detailImages.length
    if (availableSlots <= 0) {
      setSelectionError(`侧面/细节图最多上传 ${SUBJECT_MAX_DETAIL_IMAGES} 张。`)
      return
    }
    const accepted = chosen.slice(0, availableSlots)
    setSelectionError(chosen.length > availableSlots
      ? `侧面/细节图最多上传 ${SUBJECT_MAX_DETAIL_IMAGES} 张，已保留本次选择中的前 ${accepted.length} 张。`
      : '')
    onUploadedFilesChange({
      ...uploadedFiles,
      detailImages: [...uploadedFiles.detailImages, ...accepted],
    })
  }

  const selectSingleImage = (
    field: 'frontalImage' | 'backImage',
    event: ChangeEvent<HTMLInputElement>,
  ) => {
    const file = event.currentTarget.files?.[0] ?? null
    event.currentTarget.value = ''
    selectSingleFile(field, file)
  }

  const selectDetailImages = (event: ChangeEvent<HTMLInputElement>) => {
    const chosen = Array.from(event.currentTarget.files ?? [])
    event.currentTarget.value = ''
    selectDetailFiles(chosen)
  }

  const selectPanelDropFiles = (chosen: File[]) => {
    if (!chosen.length) return
    const result = fillSubjectDropSlots(uploadedFiles, chosen)
    if (!result.acceptedCount) {
      setSelectionError('主体参考图已满，请先移除图片再添加。')
      return
    }
    if (mode !== 'upload') changeMode('upload')
    setSelectionError(result.acceptedCount < chosen.length
      ? `主体参考图最多上传 ${2 + SUBJECT_MAX_DETAIL_IMAGES} 张，已保留本次拖入的前 ${result.acceptedCount} 张。`
      : '')
    onUploadedFilesChange(result.files)
  }

  const selectHistoryElement = (elementId: string) => {
    setSelectionError('')
    onSelectedElementIdChange(elementId)
  }

  const reorderSubjectFiles = (source: SubjectDragSlot, target: SubjectDragSlot) => {
    if (disabled || (source.slot === target.slot && source.index === target.index)) return
    const next = swapSubjectReferenceFiles(uploadedFiles, source, target)
    if (next === uploadedFiles) return
    setSelectionError('')
    if (mode !== 'upload') changeMode('upload')
    onUploadedFilesChange(next)
  }

  const errorId = `${id}-error`
  return <section
    className={panelClassName}
    aria-labelledby={`${id}-title`}
    aria-describedby={panelErrors.length ? errorId : undefined}
    aria-disabled={disabled || undefined}
    onDragOver={(event) => {
      if (!Array.from(event.dataTransfer.types).includes('Files')) return
      event.preventDefault()
      event.dataTransfer.dropEffect = disabled || isSubjectPanelDropExcluded(event.target)
        ? 'none'
        : 'copy'
    }}
    onDrop={(event) => {
      if (!Array.from(event.dataTransfer.types).includes('Files')) return
      event.preventDefault()
      if (disabled || isSubjectPanelDropExcluded(event.target)) return
      selectPanelDropFiles(Array.from(event.dataTransfer.files))
    }}
  >
    <header className="subject-input-panel__header">
      <div>
        <span className="subject-input-panel__eyebrow">可选</span>
        <h2 id={`${id}-title`}>一致性主体</h2>
      </div>
      <div className="subject-input-panel__header-actions" role="group" aria-label="主体来源">
        <button
          type="button"
          className={mode === 'history' ? 'is-selected' : ''}
          disabled={disabled}
          aria-pressed={mode === 'history'}
          onClick={() => changeMode(mode === 'history' ? 'none' : 'history')}
        >
          <History aria-hidden="true" size={15} />
          历史主体
        </button>
        {mode !== 'none' ? <button
          type="button"
          className="subject-input-panel__clear"
          disabled={disabled}
          onClick={clearSubject}
          aria-label="清除主体"
        >
          <X aria-hidden="true" size={15} />
        </button> : null}
      </div>
    </header>

    {mode !== 'history' ? <div className="subject-input-panel__upload">
      <div className="subject-upload-grid">
        <UploadTile
          id={`${id}-front`}
          label="正面图"
          required
          file={uploadedFiles.frontalImage}
          disabled={disabled}
          invalid={Boolean(validation.fieldErrors.frontalImage)}
          onChange={(event) => selectSingleImage('frontalImage', event)}
          onDrop={(files) => selectSingleFile('frontalImage', files[0] ?? null)}
          dragSource={{ slot: 'frontalImage' }}
          onInternalDrop={(source) => reorderSubjectFiles(source, { slot: 'frontalImage' })}
          onRemove={() => onUploadedFilesChange({ ...uploadedFiles, frontalImage: null })}
        />
        <UploadTile
          id={`${id}-back`}
          label="背面图"
          file={uploadedFiles.backImage}
          disabled={disabled}
          onChange={(event) => selectSingleImage('backImage', event)}
          onDrop={(files) => selectSingleFile('backImage', files[0] ?? null)}
          dragSource={{ slot: 'backImage' }}
          onInternalDrop={(source) => reorderSubjectFiles(source, { slot: 'backImage' })}
          onRemove={() => onUploadedFilesChange({ ...uploadedFiles, backImage: null })}
        />
        <DetailUploadTile
          id={`${id}-details`}
          files={uploadedFiles.detailImages}
          disabled={disabled}
          invalid={Boolean(validation.fieldErrors.detailImages)}
          onChange={selectDetailImages}
          onDrop={selectDetailFiles}
          onInternalDrop={(source, targetIndex) => reorderSubjectFiles(source, {
            slot: 'detailImages',
            ...(targetIndex === undefined ? {} : { index: targetIndex }),
          })}
          onRemove={(index) => onUploadedFilesChange({
            ...uploadedFiles,
            detailImages: uploadedFiles.detailImages.filter((_, fileIndex) => fileIndex !== index),
          })}
        />
      </div>

    </div> : null}

    {mode === 'history' ? <div className="subject-input-panel__history">
      {elementsLoading ? <div className="subject-input-panel__history-state" role="status">
        <LoaderCircle className="spin" aria-hidden="true" size={17} />
        <span>正在加载历史主体…</span>
      </div> : null}

      {!elementsLoading && usableElements.length ? <>
        <div className="subject-history-grid" role="group" aria-label="可用历史主体">
          {visibleElements.map((element) => {
            const isSelected = element.id === selectedElementId
            return <button
              key={element.id}
              type="button"
              className={`subject-history-card${isSelected ? ' is-selected' : ''}`}
              disabled={disabled}
              aria-pressed={isSelected}
              onClick={() => selectHistoryElement(element.id)}
            >
              <span className="subject-history-card__media">
                {element.imageUrls[0]
                  ? <img src={element.imageUrls[0]} alt="" loading="lazy" />
                  : <PackageOpen aria-hidden="true" size={22} />}
              </span>
              <strong title={element.name || element.id}>{element.name || element.id}</strong>
            </button>
          })}
        </div>
        {usableElements.length > COLLAPSED_HISTORY_COUNT ? <button
          type="button"
          className="subject-history-more"
          disabled={disabled}
          aria-expanded={showAllHistory}
          onClick={() => setShowAllHistory((current) => !current)}
        >
          {showAllHistory ? '收起' : `查看更多（${usableElements.length - COLLAPSED_HISTORY_COUNT}）`}
        </button> : null}
      </> : null}

      {!elementsLoading && !usableElements.length ? <div className="subject-input-panel__history-state">
        <PackageOpen aria-hidden="true" size={18} />
        <span>暂无可用历史主体</span>
      </div> : null}

      {elementsError ? <div className="subject-input-panel__local-error" role="alert">
        <AlertTriangle aria-hidden="true" size={16} />
        <span>{elementsError}</span>
      </div> : null}
    </div> : null}

    {panelErrors.length ? <div id={errorId} className="subject-input-panel__errors" role="alert">
      <AlertTriangle aria-hidden="true" size={16} />
      <div>{panelErrors.map((message) => <p key={message}>{message}</p>)}</div>
    </div> : null}
  </section>
}
