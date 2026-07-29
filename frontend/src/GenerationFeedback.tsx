import { Check, LoaderCircle, X } from 'lucide-react'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

import { FEEDBACK_OPTIONS, toggleFeedbackReason } from './feedbackOptions'
import type { CSSProperties, RefObject } from 'react'
import type { FeedbackReason, FeedbackValue } from './types'

export function GenerationFeedbackPanel({
  value,
  initialReasons,
  initialComment,
  anchorRef,
  onClose,
  onSave,
}: {
  value: FeedbackValue
  initialReasons: FeedbackReason[]
  initialComment: string | null
  anchorRef: RefObject<HTMLElement | null>
  onClose: () => void
  onSave: (reasons: FeedbackReason[], comment: string | null) => Promise<boolean>
}) {
  const panelRef = useRef<HTMLElement>(null)
  const [reasons, setReasons] = useState(initialReasons)
  const [comment, setComment] = useState(initialComment ?? '')
  const [saving, setSaving] = useState(false)
  const [mobile, setMobile] = useState(() => window.matchMedia('(max-width: 520px)').matches)
  const [position, setPosition] = useState<{ left: number; top: number; arrowLeft: number } | null>(null)
  const options = FEEDBACK_OPTIONS[value]

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    const closeOnOutsideClick = (event: PointerEvent) => {
      if (event.target instanceof Node && !panelRef.current?.contains(event.target)) onClose()
    }
    window.addEventListener('keydown', closeOnEscape)
    window.addEventListener('pointerdown', closeOnOutsideClick)
    return () => {
      window.removeEventListener('keydown', closeOnEscape)
      window.removeEventListener('pointerdown', closeOnOutsideClick)
    }
  }, [onClose])

  useEffect(() => {
    const media = window.matchMedia('(max-width: 520px)')
    const update = () => {
      setMobile(media.matches)
      document.body.classList.toggle('overlay-open', media.matches)
    }
    media.addEventListener('change', update)
    update()
    return () => {
      media.removeEventListener('change', update)
      document.body.classList.remove('overlay-open')
    }
  }, [])

  useLayoutEffect(() => {
    if (mobile) return
    const updatePosition = () => {
      const panel = panelRef.current
      const anchor = anchorRef.current
      if (!panel || !anchor) return
      const anchorBox = anchor.getBoundingClientRect()
      const appBodyBox = document.querySelector('.app-body')?.getBoundingClientRect()
      const panelWidth = panel.offsetWidth
      const panelHeight = panel.offsetHeight
      const safeLeft = Math.max(16, (appBodyBox?.left ?? 0) + 16)
      const maxLeft = Math.max(safeLeft, window.innerWidth - panelWidth - 16)
      const left = Math.min(Math.max(anchorBox.right - panelWidth, safeLeft), maxLeft)
      const above = anchorBox.top - panelHeight - 9
      const top = above >= 16
        ? above
        : Math.min(anchorBox.bottom + 9, window.innerHeight - panelHeight - 16)
      const arrowLeft = Math.min(
        Math.max(anchorBox.right - 51 - left, 18),
        panelWidth - 28,
      )
      setPosition({ left, top: Math.max(16, top), arrowLeft })
    }
    const animationFrame = window.requestAnimationFrame(updatePosition)
    window.addEventListener('resize', updatePosition)
    window.addEventListener('scroll', updatePosition, true)
    return () => {
      window.cancelAnimationFrame(animationFrame)
      window.removeEventListener('resize', updatePosition)
      window.removeEventListener('scroll', updatePosition, true)
    }
  }, [anchorRef, mobile])

  const save = async () => {
    setSaving(true)
    const saved = await onSave(reasons, comment.trim() || null)
    setSaving(false)
    if (saved) onClose()
  }

  const panelStyle = mobile
    ? undefined
    : position
      ? ({
          position: 'fixed',
          left: position.left,
          top: position.top,
          right: 'auto',
          bottom: 'auto',
          '--feedback-arrow-left': `${position.arrowLeft}px`,
        } as CSSProperties)
      : ({ visibility: 'hidden' } as CSSProperties)
  const panel = <>
    <button type="button" className="feedback-panel-scrim" onClick={onClose} aria-label="关闭详细反馈" />
    <section ref={panelRef} className={`feedback-panel ${value === 'LIKE' ? 'is-like' : 'is-dislike'}`} style={panelStyle} role="dialog" aria-label="详细反馈">
      <header>
        <div><strong>{value === 'LIKE' ? '哪些地方做得好？' : '哪些地方需要改进？'}</strong><span>可选，最多 3 项</span></div>
        <button type="button" className="icon-button" onClick={onClose} aria-label="关闭详细反馈"><X size={17} /></button>
      </header>
      <div className="feedback-reason-grid">
        {options.map((option) => {
          const selected = reasons.includes(option.value)
          return <button
            key={option.value}
            type="button"
            className={selected ? 'is-selected' : ''}
            aria-pressed={selected}
            disabled={!selected && reasons.length >= 3}
            onClick={() => setReasons((current) => toggleFeedbackReason(current, option.value))}
          >{selected ? <Check size={14} /> : null}{option.label}</button>
        })}
      </div>
      <label className="feedback-comment">
        <span>补充一句 <small>{comment.length}/160</small></span>
        <textarea value={comment} onChange={(event) => setComment(event.target.value)} maxLength={160} rows={2} placeholder="可选，例如：第一个转身很好，但最后推镜太快" />
      </label>
      <footer>
        <span>{reasons.length ? `已选择 ${reasons.length} 项` : '总体评价已记录'}</span>
        <button type="button" className="primary-button" disabled={saving} onClick={() => void save()}>{saving ? <LoaderCircle className="spin" size={16} /> : <Check size={16} />}完成</button>
      </footer>
    </section>
  </>
  return createPortal(panel, document.body)
}
