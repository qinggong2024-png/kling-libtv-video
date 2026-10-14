// 本文件由 App.tsx 拆分生成（2026-09-28 前端架构拆分 v2）。
import { AlertTriangle, Download, FileImage, LoaderCircle, Package, RefreshCw, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { fetchArtifactObjectUrl, fetchAssetObjectUrl, saveArtifact } from '../../api'
import { type Task } from '../../types'
import { type MediaFailure, classifyMediaFailure, playbackFailure } from './mediaFailure'
import { Modal } from './ui/Modal'

/**
 * 读取一个需要鉴权的素材地址。
 * 失败信息保留完整的 `MediaFailure`（含 HTTP 状态与重试语义），成功时返回 object URL。
 */
function useAuthenticatedMedia(src: string, retryToken = 0) {
  const [objectUrl, setObjectUrl] = useState('')
  const [failure, setFailure] = useState<MediaFailure | null>(null)
  useEffect(() => {
    let active = true
    let loadedUrl = ''
    queueMicrotask(() => {
      if (!active) return
      setObjectUrl('')
      setFailure(null)
    })
    void fetchAssetObjectUrl(src).then((url) => {
      loadedUrl = url
      if (active) setObjectUrl(url)
    }).catch((cause: unknown) => {
      if (active) setFailure(classifyMediaFailure(cause))
    })
    return () => {
      active = false
      if (loadedUrl) URL.revokeObjectURL(loadedUrl)
    }
  }, [src, retryToken])
  return { objectUrl, failure }
}

/** 把失败信息同步给父级（封面按钮要据此换成「重试」语义），只在值真正变化时上报一次。 */
function useFailureReporter(failure: MediaFailure | null, onFailureChange?: (failure: MediaFailure | null) => void) {
  const reportedRef = useRef<MediaFailure | null | undefined>(undefined)
  useEffect(() => {
    if (!onFailureChange) return
    if (reportedRef.current === failure) return
    reportedRef.current = failure
    onFailureChange(failure)
  }, [failure, onFailureChange])
}

export function AuthenticatedImage({ src, alt, eager = false, size = 'md', retryToken = 0, onRetry, onFailureChange }: {
  src: string
  alt: string
  eager?: boolean
  /** `sm` 用于 40–68px 的小缩略图，只留图标 + 一行结论，不塞补充说明。 */
  size?: 'sm' | 'md' | 'lg'
  retryToken?: number
  /** 只有在宿主元素不是按钮时才能传 —— 按钮不能嵌套按钮。 */
  onRetry?: () => void
  onFailureChange?: (failure: MediaFailure | null) => void
}) {
  const { objectUrl, failure } = useAuthenticatedMedia(src, retryToken)
  useFailureReporter(failure, onFailureChange)
  if (failure) {
    const className = `image-fallback image-fallback--${failure.kind} image-fallback--${size}`
    const srText = `${alt}：${failure.label}。${failure.detail}`
    // 小缩略图只有 40–68px 宽，塞不下 11px 的中文短句（会被 overflow:hidden 切成半个词），
    // 所以 sm 档只留图标 + 屏读文本，完整原因走 title 与 sr-only。
    const body = <>
      <FileImage size={size === 'sm' ? 18 : 22} aria-hidden="true" />
      {size === 'sm'
        ? <span className="sr-only">{srText}</span>
        : <>
          <strong className="image-fallback__label">{failure.label}</strong>
          <small className="image-fallback__detail">{failure.detail}</small>
        </>}
      {onRetry && failure.retryable ? <span className="image-fallback__retry"><RefreshCw size={13} aria-hidden="true" />重试</span> : null}
    </>
    const title = `${failure.label} —— ${failure.detail}`
    // 注意：这里不再用 role="status"。结果区一次会挂 9 张卡，9 个 live region 会在加载时
    // 齐声播报；失败信息改用 sr-only 文本随正常导航读出，页面级提示交给 composer 的状态横幅。
    if (onRetry && failure.retryable) {
      return <button type="button" className={className} onClick={onRetry} aria-label={`${srText}点击重试`} title={title}>{body}</button>
    }
    return <span className={className} title={title}>
      {body}
    </span>
  }
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
    {asset ? <AuthenticatedImage src={asset.thumbnailUrl} alt={`${task.title} 产品图`} eager={large} size="sm" /> : <Package size={20} />}
  </span>
}

export function VideoPreview({ artifactId, title, onClose, onOpenDetail }: {
  artifactId: string
  title: string
  onClose: () => void
  /** 失败时的第三条出口：跳到任务详情，用户可以在那里重新生成或下载其它产物。 */
  onOpenDetail?: () => void
}) {
  const [url, setUrl] = useState('')
  const [readFailure, setReadFailure] = useState<MediaFailure | null>(null)
  const [decodeFailure, setDecodeFailure] = useState<MediaFailure | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [downloadBusy, setDownloadBusy] = useState(false)
  const [downloadError, setDownloadError] = useState('')
  useEffect(() => {
    let active = true
    let loaded = ''
    queueMicrotask(() => {
      if (!active) return
      setUrl('')
      setReadFailure(null)
      setDecodeFailure(null)
    })
    void fetchArtifactObjectUrl(artifactId).then((value) => {
      loaded = value
      if (active) setUrl(value)
    }).catch((cause: unknown) => {
      if (active) setReadFailure(classifyMediaFailure(cause))
    })
    return () => { active = false; if (loaded) URL.revokeObjectURL(loaded) }
  }, [artifactId, attempt])
  const failure = readFailure ?? decodeFailure
  const retry = useCallback(() => {
    setDecodeFailure(null)
    setAttempt((value) => value + 1)
  }, [])
  const download = async () => {
    setDownloadBusy(true)
    setDownloadError('')
    try {
      await saveArtifact(artifactId, `${title}.mp4`)
    } catch (cause) {
      setDownloadError(classifyMediaFailure(cause).detail)
    } finally {
      setDownloadBusy(false)
    }
  }
  return <Modal className="modal-backdrop" labelledBy="video-title" onClose={onClose}>
    <section className="video-modal">
      <header><div><span>视频预览</span><h2 id="video-title">{title}</h2></div><button className="icon-button" onClick={onClose} aria-label="关闭预览"><X size={19} /></button></header>
      <div className="video-stage">
        {failure ? <div className={`video-error video-error--${failure.kind}`} role="alert">
          <AlertTriangle size={24} aria-hidden="true" />
          <strong>{failure.label}</strong>
          <small>{failure.detail}</small>
          <div className="video-error-actions">
            {failure.retryable ? <button type="button" className="secondary-button" onClick={retry}><RefreshCw size={15} aria-hidden="true" />重试读取</button> : null}
            <button type="button" className="secondary-button" disabled={downloadBusy} onClick={() => void download()}>{downloadBusy ? <LoaderCircle className="spin" size={15} /> : <Download size={15} aria-hidden="true" />}下载原视频</button>
            {onOpenDetail ? <button type="button" className="secondary-button" onClick={onOpenDetail}>查看任务详情</button> : null}
          </div>
          {downloadError ? <small className="video-error-download" role="alert">{downloadError}</small> : null}
        </div> : url
          ? <video src={url} controls autoPlay playsInline onError={() => setDecodeFailure(playbackFailure())} />
          : <span role="status"><LoaderCircle className="spin" size={28} />正在读取视频</span>}
      </div>
    </section>
  </Modal>
}
