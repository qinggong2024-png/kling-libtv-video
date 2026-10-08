// 本文件由 App.tsx 拆分生成（2026-09-28 前端架构拆分 v2）。
import { CheckCircle2, Download, Eye, Film, LoaderCircle, Play, RotateCcw, ShieldCheck, ThumbsDown, ThumbsUp } from 'lucide-react'
import { useRef, useState } from 'react'
import { saveArtifact, setVariantFeedback, setVariantFinalApproval } from '../../api'
import { type FeedbackValue, type Task, type Variant } from '../../types'
import { GenerationFeedbackPanel } from '../../GenerationFeedback'
import { StatusBadge } from '../../shared/components/Badges'
import { AuthenticatedImage } from '../../shared/components/Media'
import { formatTime, variantDisplayName, variantFileToken, variantLabelClass, variantShortLabel } from '../../domain/taskPresentation'

export function ResultCard({ task, variant, onPlay, onRemix, onOpen, onFeedbackChanged, canReview = false }: { task: Task; variant: Variant; onPlay: () => void; onRemix: () => void; onOpen: () => void; onFeedbackChanged: (task: Task) => void; canReview?: boolean }) {
  const product = [...task.assets].sort((a, b) => a.order - b.order)[0]
  const ready = Boolean(variant.downloadArtifactId)
  const [feedbackBusy, setFeedbackBusy] = useState<FeedbackValue | null>(null)
  const [feedbackMessage, setFeedbackMessage] = useState('')
  const [animatedFeedback, setAnimatedFeedback] = useState<FeedbackValue | null>(null)
  const [feedbackPanel, setFeedbackPanel] = useState<FeedbackValue | null>(null)
  const [downloadBusy, setDownloadBusy] = useState(false)
  const [downloadError, setDownloadError] = useState('')
  const [reviewOpen, setReviewOpen] = useState(false)
  const [reviewBusy, setReviewBusy] = useState(false)
  const [productFidelityPass, setProductFidelityPass] = useState(false)
  const [editingAssemblyPass, setEditingAssemblyPass] = useState(false)
  const [humanCriticalPass, setHumanCriticalPass] = useState(false)
  const [reviewNotes, setReviewNotes] = useState('')
  const reviewStartedAtRef = useRef<number | null>(null)
  const feedbackAnchorRef = useRef<HTMLDivElement>(null)
  const submitFeedback = async (value: FeedbackValue) => {
    const nextValue = variant.feedback === value ? null : value
    setFeedbackBusy(value)
    setFeedbackMessage('')
    try {
      const changed = await setVariantFeedback(task.id, variant.id, nextValue)
      onFeedbackChanged(changed)
      setAnimatedFeedback(nextValue)
      setFeedbackPanel(nextValue)
      setFeedbackMessage(nextValue ? '已记录，可选择具体原因' : '已取消反馈')
      window.setTimeout(() => setAnimatedFeedback(null), 320)
    } catch (cause) {
      setFeedbackMessage(cause instanceof Error ? cause.message : '反馈提交失败，请重试')
    } finally {
      setFeedbackBusy(null)
    }
  }
  const saveFeedbackDetails = async (reasons: Variant['feedbackReasons'], comment: string | null) => {
    if (!feedbackPanel) return false
    setFeedbackBusy(feedbackPanel)
    setFeedbackMessage('')
    try {
      const changed = await setVariantFeedback(task.id, variant.id, feedbackPanel, { reasons, comment })
      onFeedbackChanged(changed)
      setFeedbackMessage('详细反馈已保存，将优化后续同类场景')
      return true
    } catch (cause) {
      setFeedbackMessage(cause instanceof Error ? cause.message : '详细反馈保存失败，请重试')
      return false
    } finally {
      setFeedbackBusy(null)
    }
  }
  const download = async () => {
    if (!variant.downloadArtifactId) return
    setDownloadBusy(true)
    setDownloadError('')
    try {
      await saveArtifact(variant.downloadArtifactId, `${task.title}-${variantFileToken(variant)}.mp4`)
    } catch (cause) {
      setDownloadError(cause instanceof Error ? cause.message : '视频下载失败，请稍后重试')
    } finally {
      setDownloadBusy(false)
    }
  }
  const openReview = () => {
    reviewStartedAtRef.current = performance.now()
    setReviewOpen(true)
    setFeedbackMessage('')
  }
  const submitFinalApproval = async (decision: 'APPROVED' | 'REJECTED') => {
    if (decision === 'REJECTED' && !reviewNotes.trim()) {
      setFeedbackMessage('拒绝交付必须填写审核原因')
      return
    }
    setReviewBusy(true)
    setFeedbackMessage('')
    try {
      const startedAt = reviewStartedAtRef.current ?? performance.now() - 1000
      const changed = await setVariantFinalApproval(task.id, variant.id, {
        decision,
        productFidelityPass,
        editingAssemblyPass,
        humanCriticalPass,
        humanReviewSeconds: Math.max(1, Math.round((performance.now() - startedAt) / 1000)),
        expectedStateVersion: task.stateVersion,
        notes: reviewNotes.trim() || null,
      })
      onFeedbackChanged(changed)
      setReviewOpen(false)
      setFeedbackMessage(decision === 'APPROVED' ? '最终审核通过，已进入正式交付集合' : '已拒绝交付并保存质量 Ground Truth')
    } catch (cause) {
      setFeedbackMessage(cause instanceof Error ? cause.message : '最终审核提交失败，请重试')
    } finally {
      setReviewBusy(false)
    }
  }
  return <article className={`result-card${feedbackPanel ? ' has-feedback-panel' : ''}`}>
    <button className="result-cover" onClick={ready ? onPlay : onOpen} aria-label={ready ? `播放 ${task.title}` : `查看 ${task.title}`}>
      {product ? <AuthenticatedImage src={product.thumbnailUrl} alt={`${task.title} 视频封面`} /> : <Film size={30} />}
      <span className={`variant-label ${variantLabelClass(variant)}`}>{variantShortLabel(variant)}</span>
      {ready ? <span className="play-button"><Play size={21} fill="currentColor" /></span> : <span className="result-state"><StatusBadge value={variant.generationStatus} retryable={variant.retryable ?? variant.providerErrorRetryable} hasArtifact={ready} /></span>}
      {typeof task.settings?.durationSeconds === 'number' ? <span className="duration">{task.settings.durationSeconds}s</span> : null}
    </button>
    <div className="result-body"><div><strong>{task.title}</strong><span>{variantDisplayName(variant)} · {formatTime(task.updatedAt)}</span></div>
    {ready ? <div ref={feedbackAnchorRef} className="result-feedback">
      <div className={`final-approval-status is-${variant.finalApprovalStatus?.toLowerCase() ?? 'pending'}`}>
        <ShieldCheck size={16} />
        <span>{variant.finalApprovalStatus === 'APPROVED' ? '已批准交付' : variant.finalApprovalStatus === 'REJECTED' ? '交付已拒绝' : '等待 Required Hard Gates 人工审核'}</span>
        {canReview && variant.finalApprovalStatus !== 'APPROVED' ? <button type="button" className="compact-button" onClick={openReview}>质量审核</button> : null}
      </div>
      {reviewOpen ? <section className="final-approval-panel" aria-label="最终视频质量审核">
        <strong>最终交付审核</strong>
        <p>技术关键项已由系统验证；请逐项核对尚未机器验证的 Required Hard Gates。</p>
        <label><input type="checkbox" checked={productFidelityPass} onChange={(event) => setProductFidelityPass(event.target.checked)} />商品颜色、图案、Logo、文字和服装结构与源素材一致</label>
        <label><input type="checkbox" checked={editingAssemblyPass} onChange={(event) => setEditingAssemblyPass(event.target.checked)} />成片已真实完成所需镜头剪辑／组装，不是单段占位结果</label>
        <label><input type="checkbox" checked={humanCriticalPass} onChange={(event) => setHumanCriticalPass(event.target.checked)} />人物、手脸、动作、镜头与成片观感无关键缺陷</label>
        <label><span>审核备注{reviewNotes.trim() ? '' : '（拒绝时必填）'}</span><textarea value={reviewNotes} maxLength={500} onChange={(event) => setReviewNotes(event.target.value)} /></label>
        <div><button type="button" className="secondary-button" disabled={reviewBusy} onClick={() => void submitFinalApproval('REJECTED')}>拒绝交付</button><button type="button" className="primary-button" disabled={reviewBusy || !productFidelityPass || !editingAssemblyPass || !humanCriticalPass} onClick={() => void submitFinalApproval('APPROVED')}>{reviewBusy ? <LoaderCircle className="spin" size={16} /> : <CheckCircle2 size={16} />}批准交付</button></div>
      </section> : null}
      <span className="feedback-copy" aria-live="polite">{feedbackMessage || (variant.feedback ? '感谢反馈，系统会持续学习' : '这个结果怎么样？')}</span>
      <span className="feedback-buttons">
        <button className={`feedback-button${variant.feedback === 'LIKE' ? ' is-selected is-positive' : ''}${animatedFeedback === 'LIKE' ? ' is-animating' : ''}`} disabled={feedbackBusy !== null} onClick={() => void submitFeedback('LIKE')} aria-label={variant.feedback === 'LIKE' ? '取消点赞' : '点赞此视频'} aria-pressed={variant.feedback === 'LIKE'} title="点赞"><span>{feedbackBusy === 'LIKE' ? <LoaderCircle className="spin" size={17} /> : <ThumbsUp size={18} />}</span></button>
        <button className={`feedback-button${variant.feedback === 'DISLIKE' ? ' is-selected is-negative' : ''}${animatedFeedback === 'DISLIKE' ? ' is-animating' : ''}`} disabled={feedbackBusy !== null} onClick={() => void submitFeedback('DISLIKE')} aria-label={variant.feedback === 'DISLIKE' ? '取消点踩' : '点踩此视频'} aria-pressed={variant.feedback === 'DISLIKE'} title="点踩"><span>{feedbackBusy === 'DISLIKE' ? <LoaderCircle className="spin" size={17} /> : <ThumbsDown size={18} />}</span></button>
      </span>
      {feedbackPanel ? <GenerationFeedbackPanel
        key={`${variant.id}-${feedbackPanel}`}
        value={feedbackPanel}
        initialReasons={variant.feedback === feedbackPanel ? (variant.feedbackReasons ?? []) : []}
        initialComment={variant.feedback === feedbackPanel ? variant.feedbackComment : null}
        anchorRef={feedbackAnchorRef}
        onClose={() => setFeedbackPanel(null)}
        onSave={saveFeedbackDetails}
      /> : null}
    </div> : null}
    <div className="result-actions">
      {ready ? <><button className="icon-button" onClick={onPlay} aria-label="播放视频" title="播放"><Play size={17} /></button><button className="icon-button" disabled={downloadBusy} onClick={() => void download()} aria-label="下载视频" title="下载">{downloadBusy ? <LoaderCircle className="spin" size={17} /> : <Download size={17} />}</button><button className="icon-button" onClick={onOpen} aria-label="查看任务详情" title="查看任务详情"><Eye size={17} /></button></> : <button className="compact-button" onClick={onOpen}>查看状态</button>}
      <button className="remix-button" onClick={onRemix}><RotateCcw size={15} />同素材再制作</button>
    </div>{downloadError ? <small className="result-action-error" role="alert">{downloadError}</small> : null}</div>
  </article>
}
