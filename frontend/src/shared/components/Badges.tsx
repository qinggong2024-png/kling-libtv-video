// 本文件由 App.tsx 拆分生成（2026-09-28 前端架构拆分 v2）。
// 代码为逐字搬运，未经逻辑改写。
import { type Task } from '../../types'
import { providerPresentation } from '../../providerPresentation'
import { statusMeta } from '../../domain/workflowStates'
import { taskStatus } from '../../domain/taskPresentation'

export function StatusBadge({ value }: { value: string | null }) {
  if (!value) return <span className="status status--neutral"><span />状态待确认</span>
  const meta = statusMeta[value] ?? { label: value, tone: 'neutral' as const }
  return <span className={`status status--${meta.tone}`}><span />{meta.label}</span>
}

export function ProviderBadge({ provider }: { provider: string }) {
  const meta = providerPresentation(provider)
  return <span className={`provider-badge ${meta.cssClass}`}>{meta.displayLabel}</span>
}

export function TaskStatusBadge({ task }: { task: Task }) {
  const meta = taskStatus(task)
  return <span className={`status status--${meta.tone}`}><span />{meta.label}</span>
}
