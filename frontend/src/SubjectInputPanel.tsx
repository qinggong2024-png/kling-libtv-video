import {
  AlertTriangle,
  History,
  ImagePlus,
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
import { getKlingElementStatusLabel, isKlingElementAvailable } from './klingElementStatus'
import type { KlingElement } from './types'

const COLLAPSED_HISTORY_COUNT = 6

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

function fileKey(file: File, slot: string): string {
  return `${slot}-${file.name}-${file.size}-${file.lastModified}`
}

function FileThumbnail({ file, alt }: { file: File; alt: string }) {
  const [previewUrl] = useState(() => {
    try {
      return URL.createObjectURL(file)
    } catch {
      return ''
    }
  })

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl)
    }
  }, [previewUrl])

  return previewUrl
    ? <img src={previewUrl} alt={alt} />
    : <ImagePlus aria-hidden="true" size={22} />
}

function UploadTile({
  id,
  label,
  hint,
  required,
  file,
  disabled,
  describedBy,
  invalid,
  onChange,
  onRemove,
}: {
  id: string
  label: string
  hint: string
  required?: boolean
  file: File | null
  disabled: boolean
  describedBy: string
  invalid?: boolean
  onChange: (event: ChangeEvent<HTMLInputElement>) => void
  onRemove: () => void
}) {
  return <div className={`subject-upload-tile${file ? ' is-filled' : ''}${required ? ' is-required' : ''}`}>
    <div className="subject-upload-tile__heading">
      <strong>{label}</strong>
      <span>{required ? '必选' : '可选'}</span>
    </div>
    <div className="subject-upload-tile__media">
      {file
        ? <FileThumbnail key={fileKey(file, id)} file={file} alt={`${label}预览`} />
        : <ImagePlus aria-hidden="true" size={24} />}
    </div>
    <small>{file ? file.name : hint}</small>
    <div className="subject-upload-tile__actions">
      <label className="subject-upload-tile__pick" htmlFor={id}>
        {file ? '更换' : '选择图片'}
      </label>
      {file ? <button
        type="button"
        disabled={disabled}
        onClick={onRemove}
        aria-label={`移除${label}“${file.name}”`}
      >
        <X aria-hidden="true" size={15} />
      </button> : null}
    </div>
    <input
      id={id}
      className="sr-only"
      type="file"
      accept={SUBJECT_IMAGE_ACCEPT}
      disabled={disabled}
      aria-describedby={describedBy}
      aria-invalid={invalid || undefined}
      onChange={onChange}
    />
  </div>
}

function DetailUploadTile({
  id,
  files,
  disabled,
  describedBy,
  invalid,
  onChange,
  onRemove,
}: {
  id: string
  files: File[]
  disabled: boolean
  describedBy: string
  invalid?: boolean
  onChange: (event: ChangeEvent<HTMLInputElement>) => void
  onRemove: (index: number) => void
}) {
  const isFull = files.length >= SUBJECT_MAX_DETAIL_IMAGES
  return <div className={`subject-upload-tile subject-upload-tile--details${files.length ? ' is-filled' : ''}`}>
    <div className="subject-upload-tile__heading">
      <strong>侧面/细节</strong>
      <span>{files.length}/{SUBJECT_MAX_DETAIL_IMAGES}</span>
    </div>
    <div className="subject-upload-tile__media subject-upload-tile__media--details">
      {files.length
        ? files.map((file, index) => <div className="subject-upload-tile__detail" key={fileKey(file, `detail-${index}`)}>
            <FileThumbnail file={file} alt={`侧面或细节图 ${index + 1} 预览`} />
            <button
              type="button"
              disabled={disabled}
              onClick={() => onRemove(index)}
              aria-label={`移除侧面或细节图“${file.name}”`}
            >
              <X aria-hidden="true" size={14} />
            </button>
          </div>)
        : <ImagePlus aria-hidden="true" size={24} />}
    </div>
    <small>{files.length ? `${files.length} 张已选择` : '最多 2 张，可选'}</small>
    {!isFull ? <label className="subject-upload-tile__pick" htmlFor={id}>
      {files.length ? '继续添加' : '选择图片'}
    </label> : null}
    <input
      id={id}
      className="sr-only"
      type="file"
      multiple
      accept={SUBJECT_IMAGE_ACCEPT}
      disabled={disabled || isFull}
      aria-describedby={describedBy}
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
  const panelClassName = ['subject-input-panel', className].filter(Boolean).join(' ')

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

  const selectSingleImage = (
    field: 'frontalImage' | 'backImage',
    event: ChangeEvent<HTMLInputElement>,
  ) => {
    const file = event.currentTarget.files?.[0] ?? null
    event.currentTarget.value = ''
    if (!file) return
    setSelectionError('')
    onUploadedFilesChange({ ...uploadedFiles, [field]: file })
  }

  const selectDetailImages = (event: ChangeEvent<HTMLInputElement>) => {
    const chosen = Array.from(event.currentTarget.files ?? [])
    event.currentTarget.value = ''
    if (!chosen.length) return
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

  const selectHistoryElement = (elementId: string) => {
    setSelectionError('')
    onSelectedElementIdChange(elementId)
  }

  const errorId = `${id}-error`
  const uploadHelpId = `${id}-upload-help`
  return <section
    className={panelClassName}
    aria-labelledby={`${id}-title`}
    aria-describedby={panelErrors.length ? errorId : undefined}
    aria-disabled={disabled || undefined}
  >
    <header className="subject-input-panel__header">
      <div>
        <span className="subject-input-panel__eyebrow">可选</span>
        <h2 id={`${id}-title`}>一致性主体</h2>
        <p>留空也可直接生成。</p>
      </div>
      <PackageOpen aria-hidden="true" size={20} />
    </header>

    <div className="subject-input-panel__quick-actions" role="group" aria-label="选择主体来源">
      <button
        type="button"
        className={mode === 'upload' ? 'is-selected' : ''}
        disabled={disabled}
        aria-pressed={mode === 'upload'}
        onClick={() => changeMode('upload')}
      >
        <ImagePlus aria-hidden="true" size={16} />
        上传新主体
      </button>
      <button
        type="button"
        className={mode === 'history' ? 'is-selected' : ''}
        disabled={disabled}
        aria-pressed={mode === 'history'}
        onClick={() => changeMode('history')}
      >
        <History aria-hidden="true" size={16} />
        历史主体
      </button>
      {mode !== 'none' ? <button
        type="button"
        className="subject-input-panel__clear"
        disabled={disabled}
        onClick={clearSubject}
      >
        <X aria-hidden="true" size={15} />
        清除主体
      </button> : null}
    </div>

    {mode === 'upload' ? <div className="subject-input-panel__upload">
      <p id={uploadHelpId} className="subject-input-panel__help">
        正面图必选，共上传 2–4 张 JPG/PNG。
      </p>
      <div className="subject-upload-grid">
        <UploadTile
          id={`${id}-front`}
          label="正面图"
          hint="清晰、完整"
          required
          file={uploadedFiles.frontalImage}
          disabled={disabled}
          describedBy={uploadHelpId}
          invalid={Boolean(validation.fieldErrors.frontalImage)}
          onChange={(event) => selectSingleImage('frontalImage', event)}
          onRemove={() => onUploadedFilesChange({ ...uploadedFiles, frontalImage: null })}
        />
        <UploadTile
          id={`${id}-back`}
          label="背面图"
          hint="补充版型"
          file={uploadedFiles.backImage}
          disabled={disabled}
          describedBy={uploadHelpId}
          onChange={(event) => selectSingleImage('backImage', event)}
          onRemove={() => onUploadedFilesChange({ ...uploadedFiles, backImage: null })}
        />
        <DetailUploadTile
          id={`${id}-details`}
          files={uploadedFiles.detailImages}
          disabled={disabled}
          describedBy={uploadHelpId}
          invalid={Boolean(validation.fieldErrors.detailImages)}
          onChange={selectDetailImages}
          onRemove={(index) => onUploadedFilesChange({
            ...uploadedFiles,
            detailImages: uploadedFiles.detailImages.filter((_, fileIndex) => fileIndex !== index),
          })}
        />
      </div>

      <div
        className={`subject-input-panel__validation ${validation.isValid ? 'is-valid' : 'is-incomplete'}`}
        role={validation.isValid ? 'status' : undefined}
      >
        <span>{validation.fileCount}/{SUBJECT_MAX_DETAIL_IMAGES + 2} 张</span>
        <p>{validation.isValid
          ? '图片齐全，主体信息将自动生成。'
          : validation.errors[0]}</p>
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

    <footer className="subject-input-panel__footer">
      <div
        className={`subject-reference-budget ${budget.isValid ? '' : 'is-over-limit'}`}
        aria-live="polite"
      >
        <span>引用</span>
        <strong>{budget.used}/{budget.limit}</strong>
        <small>
          {budget.storyboardCount} 张分镜
          {budget.subjectCount
            ? mode === 'history'
              ? ' + 1 个主体'
              : ` + ${budget.subjectCount} 张主体图`
            : '，未使用主体'}
        </small>
      </div>
    </footer>

    {panelErrors.length ? <div id={errorId} className="subject-input-panel__errors" role="alert">
      <AlertTriangle aria-hidden="true" size={16} />
      <div>{panelErrors.map((message) => <p key={message}>{message}</p>)}</div>
    </div> : null}
  </section>
}
