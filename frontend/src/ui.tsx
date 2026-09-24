import { AlertTriangle, CheckCircle2, Info, X } from 'lucide-react'
import { useEffect, useId, useRef } from 'react'
import type { ReactNode } from 'react'
import type { StatusTone } from './types'

export type FoundationStatus = {
  label: string
  tone: StatusTone
}

const statusIcons: Record<StatusTone, typeof Info> = {
  neutral: Info,
  active: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  danger: AlertTriangle,
}

/** Shared status token. Keep the tone semantic; do not use it as a brand color. */
export function FoundationStatusBadge({ status, live = false }: { status: FoundationStatus; live?: boolean }) {
  const Icon = statusIcons[status.tone]
  return <span className={`foundation-status foundation-status--${status.tone}`} role={live ? 'status' : undefined} aria-live={live ? 'polite' : undefined}>
    <Icon size={14} aria-hidden="true" />
    <span>{status.label}</span>
  </span>
}

export function FoundationEmptyState({ icon, title, description, action }: { icon?: ReactNode; title: string; description?: string; action?: ReactNode }) {
  return <section className="foundation-empty-state" aria-label={title}>
    {icon ? <span className="foundation-empty-state__icon" aria-hidden="true">{icon}</span> : null}
    <h2>{title}</h2>
    {description ? <p>{description}</p> : null}
    {action ? <div className="foundation-empty-state__action">{action}</div> : null}
  </section>
}

export function FoundationAlert({ tone = 'warning', title, children, live = false }: { tone?: Exclude<StatusTone, 'active' | 'neutral'>; title?: string; children: ReactNode; live?: boolean }) {
  const Icon = tone === 'danger' ? AlertTriangle : tone === 'success' ? CheckCircle2 : Info
  return <div className={`foundation-alert foundation-alert--${tone}`} role={tone === 'danger' ? 'alert' : live ? 'status' : undefined} aria-live={live ? 'polite' : undefined}>
    <Icon size={16} aria-hidden="true" />
    <div>{title ? <strong>{title}</strong> : null}<span>{children}</span></div>
  </div>
}

export function FoundationThumbnail({ src, alt, ratio = 'square', fit = 'contain', fallback }: { src?: string | null; alt: string; ratio?: 'square' | 'portrait' | 'landscape' | 'video'; fit?: 'contain' | 'cover'; fallback?: ReactNode }) {
  return <figure className={`foundation-thumbnail foundation-thumbnail--${ratio} foundation-thumbnail--${fit}`}>
    {src ? <img src={src} alt={alt} loading="lazy" /> : <span aria-label={alt}>{fallback ?? '暂无预览'}</span>}
  </figure>
}

export function FoundationConfirmPanel({ title, description, confirmLabel = '确认', cancelLabel = '取消', busy = false, onConfirm, onCancel, children }: { title: string; description?: string; confirmLabel?: string; cancelLabel?: string; busy?: boolean; onConfirm: () => void; onCancel?: () => void; children?: ReactNode }) {
  const titleId = useId()
  return <section className="foundation-confirm-panel" aria-labelledby={titleId}>
    <div><h2 id={titleId}>{title}</h2>{description ? <p>{description}</p> : null}{children}</div>
    <div className="foundation-confirm-panel__actions">
      {onCancel ? <button type="button" className="secondary-button" disabled={busy} onClick={onCancel}>{cancelLabel}</button> : null}
      <button type="button" className="primary-button" disabled={busy} onClick={onConfirm}>{confirmLabel}</button>
    </div>
  </section>
}

export function FoundationDrawer({ open, title, eyebrow, onClose, children, footer }: { open: boolean; title: string; eyebrow?: string; onClose: () => void; children: ReactNode; footer?: ReactNode }) {
  const titleId = useId()
  const dialogRef = useRef<HTMLDialogElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (!open) return
    const dialog = dialogRef.current
    if (!dialog) return
    const previous = document.activeElement as HTMLElement | null
    const wasLocked = document.body.classList.contains('overlay-open')
    document.body.classList.add('overlay-open')
    dialog.showModal()
    closeRef.current?.focus()
    return () => {
      dialog.close()
      if (!wasLocked) document.body.classList.remove('overlay-open')
      if (previous?.isConnected) previous.focus()
    }
  }, [open])
  if (!open) return null
  return <dialog ref={dialogRef} className="foundation-drawer-backdrop" aria-labelledby={titleId} onCancel={(event) => { event.preventDefault(); onClose() }} onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
    <section className="foundation-drawer">
      <header className="foundation-drawer__header"><div>{eyebrow ? <span>{eyebrow}</span> : null}<h2 id={titleId}>{title}</h2></div><button ref={closeRef} type="button" className="icon-button" onClick={onClose} aria-label="关闭"><X size={18} /></button></header>
      <div className="foundation-drawer__content">{children}</div>
      {footer ? <footer className="foundation-drawer__footer">{footer}</footer> : null}
    </section>
  </dialog>
}
