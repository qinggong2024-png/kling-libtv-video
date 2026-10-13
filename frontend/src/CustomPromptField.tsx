import { AlertTriangle, Check, LoaderCircle, Pencil, Plus, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { createPortal } from 'react-dom'
import { Modal } from './shared/components/ui/Modal'

import {
  createPromptPreset,
  deletePromptPreset,
  getPromptPresets,
  updatePromptPreset,
} from './api'
import type { PromptPreset, PromptPresetScope, PromptPresetWrite } from './types'

function PromptPresetDialog({ scope, target, initialContent, onClose, onSave, onDelete }: {
  scope: PromptPresetScope
  target: PromptPreset | null
  initialContent: string
  onClose: () => void
  onSave: (payload: PromptPresetWrite) => Promise<void>
  onDelete: ((preset: PromptPreset) => Promise<void>) | null
}) {
  const [name, setName] = useState(target?.name ?? '')
  const [content, setContent] = useState(target?.content ?? initialContent)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(false)

  const save = async (event: FormEvent) => {
    event.preventDefault()
    if (!name.trim() || !content.trim()) return
    setBusy(true)
    setError('')
    try {
      await onSave({ scope, name: name.trim(), content: content.trim(), sortOrder: target?.sortOrder ?? 0 })
      onClose()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '提示词方案保存失败')
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    if (!target || !onDelete) return
    if (!confirmDelete) {
      setConfirmDelete(true)
      return
    }
    setBusy(true)
    setError('')
    try {
      await onDelete(target)
      onClose()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '提示词方案删除失败')
      setBusy(false)
    }
  }

  return createPortal(<Modal className="prompt-preset-overlay" labelledBy="prompt-preset-title" onClose={() => { if (!busy) onClose() }}>
    <form className="prompt-preset-dialog" onSubmit={(event) => void save(event)}>
      <header><div><span>提示词方案</span><h2 id="prompt-preset-title">{target ? '编辑方案' : '保存为新方案'}</h2></div><button type="button" className="icon-button" disabled={busy} onClick={onClose} aria-label="关闭" title="关闭"><X size={18} /></button></header>
      <label><span>方案名称</span><input name="preset-name" autoComplete="off" value={name} maxLength={80} disabled={busy} onChange={(event) => setName(event.target.value)} placeholder="例如：自然走动展示" /></label>
      <label><span>提示词内容</span><textarea name="preset-content" autoComplete="off" value={content} maxLength={2800} disabled={busy} onChange={(event) => setContent(event.target.value)} /></label>
      <div className="prompt-preset-counter">{content.length} / 2800</div>
      {error ? <div className="inline-alert inline-alert--danger" role="alert"><AlertTriangle size={16} /><span>{error}</span></div> : null}
      <footer>
        {target && onDelete ? <div className="prompt-preset-delete">{confirmDelete ? <button type="button" className="secondary-button" disabled={busy} onClick={() => setConfirmDelete(false)}>取消删除</button> : null}<button type="button" className="secondary-button secondary-button--danger" disabled={busy} onClick={() => void remove()}>{confirmDelete ? '确认删除' : '删除方案'}</button></div> : <span />}
        <div><button type="button" className="secondary-button" disabled={busy} onClick={onClose}>取消</button><button type="submit" className="primary-button" disabled={busy || !name.trim() || !content.trim()}>{busy ? <LoaderCircle className="spin" size={16} /> : <Check size={16} />}保存</button></div>
      </footer>
    </form>
  </Modal>, document.body)
}

export function CustomPromptField({ scope, label, value, disabled = false, placeholder, onChange }: {
  scope: PromptPresetScope
  label: string
  value: string
  disabled?: boolean
  placeholder: string
  onChange: (value: string) => void
}) {
  const [presets, setPresets] = useState<PromptPreset[]>([])
  const [selectedPresetId, setSelectedPresetId] = useState('')
  const [editorTarget, setEditorTarget] = useState<PromptPreset | null | undefined>(undefined)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const valueRef = useRef(value)
  const onChangeRef = useRef(onChange)

  useEffect(() => {
    valueRef.current = value
    onChangeRef.current = onChange
  }, [onChange, value])

  useEffect(() => {
    let active = true
    void getPromptPresets(scope)
      .then((items) => {
        if (!active) return
        setPresets(items)
        if (!valueRef.current.trim() && items.length) {
          setSelectedPresetId(items[0].id)
          onChangeRef.current(items[0].content)
        }
      })
      .catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : '提示词方案读取失败') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [scope])

  const savePreset = async (payload: PromptPresetWrite) => {
    const saved = editorTarget
      ? await updatePromptPreset(editorTarget.id, payload)
      : await createPromptPreset(payload)
    setPresets((current) => editorTarget
      ? current.map((item) => item.id === saved.id ? saved : item)
      : [...current, saved].sort((a, b) => a.sortOrder - b.sortOrder || a.createdAt.localeCompare(b.createdAt)))
    setSelectedPresetId(saved.id)
    onChange(saved.content)
  }

  const removePreset = async (preset: PromptPreset) => {
    await deletePromptPreset(preset.id)
    setPresets((current) => current.filter((item) => item.id !== preset.id))
    if (selectedPresetId === preset.id) setSelectedPresetId('')
  }

  return <>
    <label className="custom-prompt-field"><span>{label}</span><textarea name={`${scope}-prompt`} autoComplete="off" value={value} maxLength={2800} disabled={disabled} onChange={(event) => { onChange(event.target.value); setSelectedPresetId('') }} placeholder={placeholder} /></label>
    <div className="custom-prompt-meta"><span>{value.length} / 2800</span><span>{selectedPresetId ? `已载入：${presets.find((item) => item.id === selectedPresetId)?.name ?? ''}` : '临时草稿'}</span></div>
    <div className="prompt-preset-toolbar">
      <div className="prompt-preset-heading"><span>提示词方案</span><button type="button" className="compact-button" disabled={disabled || !value.trim()} onClick={() => setEditorTarget(null)}><Plus size={15} />保存当前方案</button></div>
      {loading ? <span className="prompt-preset-loading"><LoaderCircle className="spin" size={14} />读取中</span> : null}
      {!loading && presets.length ? <div className="prompt-preset-list">{presets.map((preset) => <span key={preset.id} className={selectedPresetId === preset.id ? 'is-selected' : ''}><button type="button" disabled={disabled} title={preset.content} onClick={() => { onChange(preset.content); setSelectedPresetId(preset.id) }}>{preset.name}</button><button type="button" className="prompt-preset-edit" disabled={disabled} onClick={() => setEditorTarget(preset)} aria-label={`编辑${preset.name}`} title="编辑方案"><Pencil size={13} /></button></span>)}</div> : null}
      {!loading && !presets.length ? <span className="prompt-preset-empty">暂无已保存方案</span> : null}
      {error ? <small className="field-error" role="alert">{error}</small> : null}
    </div>
    {editorTarget !== undefined ? <PromptPresetDialog scope={scope} target={editorTarget} initialContent={value} onClose={() => setEditorTarget(undefined)} onSave={savePreset} onDelete={editorTarget ? removePreset : null} /> : null}
  </>
}
