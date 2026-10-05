// 本文件由 App.tsx 拆分生成（2026-09-28 前端架构拆分 v2）。
// 代码为逐字搬运，未经逻辑改写。
import { CheckCircle2, CircleAlert, X } from 'lucide-react'
import { type InPageTaskToast } from '../../app/appTypes'

export function InPageTaskToasts({
  toasts,
  onOpen,
  onDismiss,
}: {
  toasts: InPageTaskToast[]
  onOpen: (toast: InPageTaskToast) => void
  onDismiss: (id: string) => void
}) {
  if (!toasts.length) return null
  return <div className="task-toast-region" aria-live="polite" aria-label="任务提醒">
    {toasts.map((toast) => <section key={toast.id} className={`task-toast task-toast--${toast.tone}`} role="status">
      <span className="task-toast-icon" aria-hidden="true">
        {toast.tone === 'success' ? <CheckCircle2 size={19} /> : <CircleAlert size={19} />}
      </span>
      <button className="task-toast-content" type="button" onClick={() => onOpen(toast)}>
        <strong>{toast.title}</strong>
        <span>{toast.body}</span>
        <small>点击查看任务</small>
      </button>
      <button className="task-toast-dismiss" type="button" aria-label={`关闭“${toast.title}”提醒`} onClick={() => onDismiss(toast.id)}>
        <X size={17} />
      </button>
    </section>)}
  </div>
}
