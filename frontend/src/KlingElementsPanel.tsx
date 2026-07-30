import { AlertTriangle, CheckCircle2, ImagePlus, LoaderCircle, RefreshCw, Trash2, UsersRound, Video } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'

import { ApiError, createKlingElement, deleteKlingElement, getKlingElements } from './api'
import {
  KLING_ELEMENT_MAX_IMAGES,
  readKlingElementImage,
  validateKlingElementImages,
  validateKlingElementVideoUrl,
} from './klingElementFiles'
import type { KlingElement } from './types'

type ReferenceMode = 'images' | 'video'

const elementStatusLabels: Record<string, string> = {
  submitted: '创建中',
  processing: '处理中',
  succeeded: '可用',
  failed: '失败',
  active: '可用',
}

export function KlingElementsPanel({ adminId }: { adminId: string }) {
  const [elements, setElements] = useState<KlingElement[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<'create' | string | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [voiceId, setVoiceId] = useState('')
  const [mode, setMode] = useState<ReferenceMode>('images')
  const [images, setImages] = useState<File[]>([])
  const [videoUrl, setVideoUrl] = useState('')
  const imageInputRef = useRef<HTMLInputElement>(null)

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true)
    try {
      const page = await getKlingElements(adminId, 1, 50, false, signal)
      if (signal?.aborted) return
      setElements(page.items)
      setTotal(page.total)
      setError('')
    } catch (cause) {
      if (signal?.aborted) return
      setError(cause instanceof ApiError ? cause.message : '无法读取可灵主体列表')
    } finally {
      if (!signal?.aborted) setLoading(false)
    }
  }, [adminId])

  useEffect(() => {
    const controller = new AbortController()
    const run = async () => {
      await load(controller.signal)
    }
    const timer = window.setTimeout(() => void run(), 0)
    return () => {
      controller.abort()
      window.clearTimeout(timer)
    }
  }, [load])

  const selectImages = (selected: File[]) => {
    const next = [...images, ...selected]
    const validationError = validateKlingElementImages(next)
    if (next.length > KLING_ELEMENT_MAX_IMAGES || validationError && !validationError.includes('2–4')) {
      setError(validationError)
      return
    }
    setImages(next)
    setError(next.length < 2 ? '请再添加至少 1 张参考图。' : '')
    setNotice('')
  }

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const normalizedName = name.trim()
    const normalizedDescription = description.trim()
    if (!normalizedName || !normalizedDescription) {
      setError('主体名称和描述不能为空。')
      return
    }
    const referenceError = mode === 'images'
      ? validateKlingElementImages(images)
      : validateKlingElementVideoUrl(videoUrl)
    if (referenceError) {
      setError(referenceError)
      return
    }
    setBusy('create')
    setError('')
    setNotice('')
    try {
      const imageReferences = mode === 'images'
        ? await Promise.all(images.map(readKlingElementImage))
        : undefined
      await createKlingElement(adminId, {
        name: normalizedName,
        description: normalizedDescription,
        ...(imageReferences ? { imageReferences } : {}),
        ...(mode === 'video' ? { videoReferences: [videoUrl.trim()] } : {}),
        ...(voiceId.trim() ? { voiceId: voiceId.trim() } : {}),
      })
      setName('')
      setDescription('')
      setVoiceId('')
      setImages([])
      setVideoUrl('')
      if (imageInputRef.current) imageInputRef.current.value = ''
      setNotice('主体已提交创建，可灵处理完成后即可用于视频任务。')
      await load()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '可灵主体创建失败')
    } finally {
      setBusy(null)
    }
  }

  const remove = async (element: KlingElement) => {
    if (!window.confirm(`确定删除主体“${element.name || element.id}”吗？`)) return
    setBusy(element.id)
    setError('')
    setNotice('')
    try {
      await deleteKlingElement(adminId, element.id)
      setElements((current) => current.filter((item) => item.id !== element.id))
      setTotal((current) => Math.max(0, current - 1))
      setNotice('主体已删除。')
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '可灵主体删除失败')
    } finally {
      setBusy(null)
    }
  }

  const formBusy = busy === 'create'
  return <section className="settings-section kling-elements-section" aria-labelledby="kling-elements-title">
    <div className="settings-section-heading">
      <div><span>主体库</span><h2 id="kling-elements-title">可灵主体管理</h2><p>创建可复用的人物或商品主体，并在固定模板视频任务中绑定。</p></div>
      <button className="secondary-button" type="button" disabled={loading || busy !== null} onClick={() => void load()}><RefreshCw className={loading ? 'spin' : ''} size={16} />刷新主体</button>
    </div>

    <form className="kling-element-form" onSubmit={(event) => void submit(event)}>
      <div className="kling-element-fields">
        <label><strong>主体名称</strong><input value={name} disabled={formBusy} maxLength={20} required onChange={(event) => setName(event.target.value)} placeholder="例如：春季女装模特" /><small>{name.length}/20</small></label>
        <label><strong>主体描述</strong><input value={description} disabled={formBusy} maxLength={100} required onChange={(event) => setDescription(event.target.value)} placeholder="简要描述人物、商品或角色特征" /><small>{description.length}/100</small></label>
        <label><strong>Voice ID</strong><input value={voiceId} disabled={formBusy} maxLength={160} onChange={(event) => setVoiceId(event.target.value)} placeholder="可选" /><small>需要复用可灵音色时填写</small></label>
      </div>
      <fieldset className="kling-element-reference">
        <legend>主体参考素材</legend>
        <div className="segmented-control">
          <label className={mode === 'images' ? 'is-selected' : ''}><input type="radio" name="element-reference-mode" checked={mode === 'images'} disabled={formBusy} onChange={() => { setMode('images'); setError('') }} /><span><ImagePlus size={15} />图像主体</span></label>
          <label className={mode === 'video' ? 'is-selected' : ''}><input type="radio" name="element-reference-mode" checked={mode === 'video'} disabled={formBusy} onChange={() => { setMode('video'); setError('') }} /><span><Video size={15} />视频主体</span></label>
        </div>
        {mode === 'images' ? <div className="kling-element-images">
          <input ref={imageInputRef} type="file" multiple accept=".jpg,.jpeg,.png,image/jpeg,image/png" disabled={formBusy || images.length >= KLING_ELEMENT_MAX_IMAGES} onChange={(event) => { selectImages(Array.from(event.currentTarget.files ?? [])); event.currentTarget.value = '' }} />
          <small>选择 2–4 张 JPG/PNG；单张不超过 10 MB，总计不超过 40 MB。图片仅在提交时转码，不在页面回显内容。</small>
          {images.length ? <ul>{images.map((file, index) => <li key={`${file.name}-${file.lastModified}-${index}`}><span>{file.name}<small>{(file.size / 1024 / 1024).toFixed(1)} MB</small></span><button type="button" className="icon-button" disabled={formBusy} onClick={() => setImages((current) => current.filter((_, itemIndex) => itemIndex !== index))} aria-label={`移除 ${file.name}`}><Trash2 size={15} /></button></li>)}</ul> : null}
        </div> : <label className="kling-element-video"><strong>参考视频 URL</strong><input type="url" value={videoUrl} disabled={formBusy} maxLength={4096} onChange={(event) => setVideoUrl(event.target.value)} placeholder="https://cdn.example.com/reference.mp4" /><small>当前支持一个可公开读取的 HTTPS 视频地址</small></label>}
      </fieldset>
      <div className="kling-element-submit">
        <span>创建主体会调用可灵官方 API，但不会直接生成视频。</span>
        <button className="primary-button" disabled={formBusy} type="submit">{formBusy ? <LoaderCircle className="spin" size={16} /> : <UsersRound size={16} />}{formBusy ? '正在创建' : '创建主体'}</button>
      </div>
    </form>

    {error ? <div className="inline-alert inline-alert--danger" role="alert"><AlertTriangle size={16} />{error}</div> : null}
    {notice ? <div className="inline-alert inline-alert--success" role="status"><CheckCircle2 size={16} />{notice}</div> : null}

    <div className="kling-element-list">
      <div className="detail-heading"><div><span className="section-kicker">已创建主体</span><h3>当前 API 凭据下的主体</h3></div><span>{total}</span></div>
      {loading && !elements.length ? <div className="account-loading"><LoaderCircle className="spin" size={20} />正在读取主体…</div>
        : elements.length ? elements.map((element) => <article key={element.id} className="kling-element-row">
          <span className="kling-element-row-icon">{element.videoUrl ? <Video size={18} /> : <UsersRound size={18} />}</span>
          <span><strong>{element.name || '未命名主体'}</strong><small>{element.description || (element.videoUrl ? '视频参考主体' : `${element.imageUrls.length} 张图像参考`)}</small><code>{element.id}</code></span>
          <span className={`status ${['succeeded', 'active'].includes(element.status.toLowerCase()) ? 'status--success' : element.status.toLowerCase() === 'failed' ? 'status--danger' : 'status--active'}`}><span />{elementStatusLabels[element.status.toLowerCase()] ?? element.status}</span>
          {element.voiceId ? <small>Voice · {element.voiceId}</small> : null}
          <button type="button" className="icon-button" disabled={busy !== null} onClick={() => void remove(element)} aria-label={`删除 ${element.name || element.id}`} title="删除主体">{busy === element.id ? <LoaderCircle className="spin" size={16} /> : <Trash2 size={16} />}</button>
        </article>) : <p className="ops-muted">尚未创建自定义主体</p>}
    </div>
  </section>
}
