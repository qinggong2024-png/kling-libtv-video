// 本文件由 App.tsx 拆分生成（2026-09-28 前端架构拆分 v2）。
import { AlertTriangle, FileImage, LoaderCircle, Package, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { fetchArtifactObjectUrl, fetchAssetObjectUrl } from '../../api'
import { type Task } from '../../types'
import { Modal } from './ui/Modal'

export function AuthenticatedImage({ src, alt, eager = false }: { src: string; alt: string; eager?: boolean }) {
  const [objectUrl, setObjectUrl] = useState('')
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    let active = true
    let loadedUrl = ''
    void fetchAssetObjectUrl(src).then((url) => {
      loadedUrl = url
      if (active) setObjectUrl(url)
    }).catch(() => { if (active) setFailed(true) })
    return () => {
      active = false
      if (loadedUrl) URL.revokeObjectURL(loadedUrl)
    }
  }, [src])
  if (failed) return <span className="image-fallback"><FileImage size={20} /><small>图片不可用</small></span>
  return objectUrl ? <img src={objectUrl} alt={alt} loading={eager ? 'eager' : 'lazy'} /> : <span className="image-skeleton" aria-label="图片加载中" />
}

export function LocalImage({ file, alt }: { file: File; alt: string }) {
  const [preview, setPreview] = useState<{ file: File; src: string } | null>(null)
  useEffect(() => {
    let active = true
    const src = URL.createObjectURL(file)
    queueMicrotask(() => {
      if (active) setPreview({ file, src })
    })
    return () => {
      active = false
      URL.revokeObjectURL(src)
    }
  }, [file])
  return preview?.file === file
    ? <img src={preview.src} alt={alt} draggable={false} />
    : <span className="image-skeleton" aria-label="图片加载中" />
}

export function ImagePreview({ file, label, onClose }: { file: File; label: string; onClose: () => void }) {
  return createPortal(<Modal className="modal-backdrop image-preview-backdrop" labelledBy="image-preview-title" onClose={onClose}>
    <section className="image-preview-modal">
      <h2 id="image-preview-title" className="sr-only">{label}：{file.name}</h2>
      <div className="image-preview-stage">
        <LocalImage file={file} alt={`${label}大图：${file.name}`} />
      </div>
      <button type="button" className="icon-button image-preview-close" onClick={onClose} aria-label="关闭图片预览" title="关闭预览"><X size={19} /></button>
    </section>
  </Modal>, document.body)
}

export function TaskThumb({ task, large = false }: { task: Task; large?: boolean }) {
  const asset = [...task.assets].sort((a, b) => a.order - b.order)[0]
  return <span className={`task-thumb ${large ? 'task-thumb--large' : ''}`}>
    {asset ? <AuthenticatedImage src={asset.thumbnailUrl} alt={`${task.title} 产品图`} eager={large} /> : <Package size={20} />}
  </span>
}

export function VideoPreview({ artifactId, title, onClose }: { artifactId: string; title: string; onClose: () => void }) {
  const [url, setUrl] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    let loaded = ''
    void fetchArtifactObjectUrl(artifactId).then((value) => { loaded = value; if (active) setUrl(value) }).catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : '视频加载失败') })
    return () => { active = false; if (loaded) URL.revokeObjectURL(loaded) }
  }, [artifactId])
  return <Modal className="modal-backdrop" labelledBy="video-title" onClose={onClose}>
    <section className="video-modal">
      <header><div><span>视频预览</span><h2 id="video-title">{title}</h2></div><button className="icon-button" onClick={onClose} aria-label="关闭预览"><X size={19} /></button></header>
      <div className="video-stage">{error ? <div className="video-error" role="alert"><AlertTriangle size={24} /><strong>{error}</strong></div> : url ? <video src={url} controls autoPlay playsInline onError={() => setError('视频无法播放，请重新打开或下载后查看。')} /> : <span role="status"><LoaderCircle className="spin" size={28} />正在读取视频</span>}</div>
    </section>
  </Modal>
}
