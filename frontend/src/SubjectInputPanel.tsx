import {
  AlertTriangle,
  History,
  LoaderCircle,
  PackageOpen,
  X,
} from 'lucide-react'
import { useId, useState } from 'react'
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

function UploadTile({
  id,
  label,
  required,
  file,
  disabled,
  invalid,
  onChange,
  onDrop,
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
  onRemove: () => void
}) {
  return <div className={`subject-upload-tile${file ? ' is-filled' : ''}${required ? ' is-required' : ''}`}>
    <label
      className="subject-upload-tile__dropzone"
      htmlFor={id}
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        event.preventDefault()
        if (!disabled) onDrop(Array.from(event.dataTransfer.files))
      }}
    >
      <strong>{label}</strong>
      <span>{file ? '已选择，点击更换' : '拖拽或选择'}</span>
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
  onRemove,
}: {
  id: string
  files: File[]
  disabled: boolean
  invalid?: boolean
  onChange: (event: ChangeEvent<HTMLInputElement>) => void
  onDrop: (files: File[]) => void
  onRemove: (index: number) => void
}) {
  const isFull = files.length >= SUBJECT_MAX_DETAIL_IMAGES
  return <div className={`subject-upload-tile subject-upload-tile--details${files.length ? ' is-filled' : ''}`}>
    <label
      className="subject-upload-tile__dropzone"
      htmlFor={id}
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        event.preventDefault()
        if (!disabled && !isFull) onDrop(Array.from(event.dataTransfer.files))
      }}
    >
      <strong>侧面图</strong>
      <span>{files.length ? `已选择 ${files.length} 张` : '拖拽或选择'}</span>
    </label>
    {files.map((file, index) => <button
      key={`${file.name}-${file.size}-${file.lastModified}`}
      type="button"
      className={`subject-upload-tile__remove subject-upload-tile__remove--detail-${index}`}
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

  const selectHistoryElement = (elementId: string) => {
    setSelectionError('')
    onSelectedElementIdChange(elementId)
  }

  const errorId = `${id}-error`
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
        <p>上传正面、背面或侧面图，建立视觉参考。</p>
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
          onRemove={() => onUploadedFilesChange({ ...uploadedFiles, frontalImage: null })}
        />
        <UploadTile
          id={`${id}-back`}
          label="背面图"
          file={uploadedFiles.backImage}
          disabled={disabled}
          onChange={(event) => selectSingleImage('backImage', event)}
          onDrop={(files) => selectSingleFile('backImage', files[0] ?? null)}
          onRemove={() => onUploadedFilesChange({ ...uploadedFiles, backImage: null })}
        />
        <DetailUploadTile
          id={`${id}-details`}
          files={uploadedFiles.detailImages}
          disabled={disabled}
          invalid={Boolean(validation.fieldErrors.detailImages)}
          onChange={selectDetailImages}
          onDrop={selectDetailFiles}
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
