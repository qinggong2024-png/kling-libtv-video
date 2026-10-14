import { Download, ExternalLink, LoaderCircle, RefreshCw, Scissors, X } from 'lucide-react'
import { useEffect, useId, useRef, useState } from 'react'
import { createCutflowHandoff, fetchAssetObjectUrl, listCutflowHandoffs, retryCutflowHandoff, saveAsset, type CutflowHandoff } from '../../api'
import { Modal } from '../../shared/components/ui/Modal'
import './cutflow.css'

function cutflowStatusLabel(status: string): string {
  return ({ QUEUED: '等待传输', READY: '准备导入', IMPORTING: '剪辑端导入中', AWAITING_EDIT: '等待剪辑配置', EDITING: '正在剪辑', PENDING_REVIEW: '剪辑版本待审核', FAILED: '交接失败', CANCELED: '剪辑已取消' } as Record<string, string>)[status] ?? '状态待确认'
}

export function CutflowControl({ taskId, variantId, artifactId, canWrite = true }: { taskId: string; variantId: string; artifactId: string; canWrite?: boolean }) {
  const [open, setOpen] = useState(false)
  const [handoffs, setHandoffs] = useState<CutflowHandoff[]>([])
  const [loaded, setLoaded] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [preview, setPreview] = useState<{ url: string; title: string } | null>(null)
  const mutation = useRef(false)
  const readVersion = useRef(0)
  const previewTrigger = useRef<HTMLButtonElement | null>(null)
  const previewTitle = useId()
  const current = handoffs.find(item => item.sourceArtifactId === artifactId)
  useEffect(() => {
    if (!open) return
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout>
    const refresh = async () => {
      const version = readVersion.current
      try {
        const result = await listCutflowHandoffs(variantId, controller.signal)
        if (!controller.signal.aborted && !mutation.current && version === readVersion.current) {
          setHandoffs(result.handoffs)
          setLoaded(result.enabled)
          setError(result.enabled ? '' : '剪辑交接尚未启用')
        }
      } catch (cause) {
        if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : '剪辑状态读取失败')
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(() => void refresh(), 15000)
      }
    }
    void refresh()
    return () => { controller.abort(); clearTimeout(timer) }
  }, [open, variantId])
  useEffect(() => {
    if (!preview && previewTrigger.current) {
      previewTrigger.current.focus()
      previewTrigger.current = null
    }
    return () => { if (preview) URL.revokeObjectURL(preview.url) }
  }, [preview])
  async function submit() {
    if (mutation.current || !loaded || !canWrite) return
    mutation.current = true
    readVersion.current += 1
    setBusy(true)
    setError('')
    try {
      const item = current?.status === 'FAILED'
        ? await retryCutflowHandoff(current.id) : await createCutflowHandoff(taskId, variantId)
      setHandoffs(previous => [item, ...previous.filter(other => other.id !== item.id)])
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '提交结果待确认，请重新读取剪辑状态')
    } finally {
      mutation.current = false
      setBusy(false)
    }
  }
  async function play(mediaUrl: string, index: number, trigger: HTMLButtonElement) {
    if (mutation.current) return
    previewTrigger.current = trigger
    mutation.current = true
    setBusy(true)
    try {
      setPreview({ url: await fetchAssetObjectUrl(mediaUrl), title: `剪辑版本 ${index + 1} · 待审核` })
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '剪辑版本读取失败')
    } finally {
      mutation.current = false
      setBusy(false)
    }
  }
  return <div className="cutflow-control">
    <button type="button" className="compact-button" onClick={() => setOpen(value => !value)} aria-expanded={open}>
      <Scissors size={16} />{current ? cutflowStatusLabel(current.status) : '继续剪辑'}
    </button>
    {open ? <div className="cutflow-control__body">
      {!loaded && !error ? <span role="status">正在读取剪辑状态</span> : null}
      {canWrite && loaded && (!current || current.status === 'FAILED') ? <button className="compact-button" type="button" disabled={busy} onClick={() => void submit()}>
        {busy ? <LoaderCircle size={16} className="spin" /> : current ? <RefreshCw size={16} /> : <Scissors size={16} />}
        {current ? '重试交接' : '发送到 Cutflow'}
      </button> : null}
      {current?.cutflowEditorUrl ? <a className="text-button" href={current.cutflowEditorUrl} target="_blank" rel="noreferrer"><ExternalLink size={16} />打开 Cutflow</a> : null}
      {current?.cutflowBatchId ? <small className="cutflow-control__batch">批次 {current.cutflowBatchId}</small> : null}
      {handoffs.flatMap(handoff => handoff.outputs).map((output, index) => <div className="cutflow-control__output" key={output.id}>
        <button type="button" className="text-button" disabled={busy} onClick={event => void play(output.mediaUrl, index, event.currentTarget)}>剪辑版本 {index + 1} · 待审核</button>
        <button type="button" className="icon-button" title={`下载剪辑版本 ${index + 1}`} aria-label={`下载剪辑版本 ${index + 1}`} disabled={busy} onClick={() => { void saveAsset(output.mediaUrl, `edited-${output.id}.mp4`).catch(cause => setError(cause instanceof Error ? cause.message : '下载失败')) }}><Download size={16} /></button>
      </div>)}
      {error || current?.errorMessage ? <small role="alert">{error || current?.errorMessage}</small> : null}
    </div> : null}
    {preview ? <Modal labelledBy={previewTitle} className="modal-backdrop" onClose={() => setPreview(null)}>
      <section className="video-modal">
        <header><h2 id={previewTitle}>{preview.title}</h2><button type="button" className="icon-button" title="关闭预览" aria-label="关闭剪辑预览" onClick={() => setPreview(null)}><X size={18} /></button></header>
        <div className="video-stage"><video src={preview.url} controls autoPlay playsInline /></div>
      </section>
    </Modal> : null}
  </div>
}
