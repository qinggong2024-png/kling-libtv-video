import type { ReactNode } from 'react'
import { Check, ChevronRight } from 'lucide-react'
import { FoundationStatusBadge } from '../ui'
import { creativeUiStatuses, type CreativeUiStatus } from '../../../features/creative-workspace/workspacePresentation'

export function CreativeStatus({ value }: { value: CreativeUiStatus }) {
  return <FoundationStatusBadge status={creativeUiStatuses[value]} />
}

export function CreativePanel({ title, subtitle, action, children }: { title: string; subtitle?: string; action?: ReactNode; children: ReactNode }) {
  return <section className="creative-panel" aria-label={title}>
    <header className="creative-panel-heading"><div><h2>{title}</h2>{subtitle ? <p>{subtitle}</p> : null}</div>{action}</header>
    {children}
  </section>
}

export function CreativeSteps({ steps, onOpen }: { steps: readonly { id: string; label: string; detail: string; evidenced: boolean }[]; onOpen: (id: string) => void }) {
  return <ol className="creative-steps" aria-label="项目生产路径">
    {steps.map((step, index) => <li key={step.id}>
      <button type="button" onClick={() => onOpen(step.id)} aria-label={`${step.label} · ${step.detail}`}>
        <span className={`creative-step-index${step.evidenced ? ' has-evidence' : ''}`}>{step.evidenced ? <Check size={14} aria-hidden="true" /> : index + 1}</span>
        <span><strong>{step.label}</strong><small>{step.detail}</small></span><ChevronRight size={14} aria-hidden="true" />
      </button>
    </li>)}
  </ol>
}

export function CreativeReviewSummary({ children }: { children: ReactNode }) {
  return <div className="creative-review-summary" role="note">{children}</div>
}
