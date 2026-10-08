import { ChevronRight } from 'lucide-react'
import type { Task } from '../../../types'
import { studioTaskPresentation } from '../../../domain/studioTaskStatus'
import { TaskThumb } from '../Media'
import { FoundationStatusBadge } from '../ui'
import { TaskElapsed } from '../TaskTiming'

export function TaskCard({ task, onOpen }: { task: Task; onOpen: () => void }) {
  const status = studioTaskPresentation(task)
  return <button type="button" className="studio-task-card" onClick={onOpen} data-task-id={task.id} data-studio-status={status.status ?? 'attention'} aria-label={`查看任务：${task.title}`}>
    <TaskThumb task={task} />
    <span className="studio-task-card__content"><strong title={task.title}>{task.title}</strong><span><FoundationStatusBadge status={status} /><TaskElapsed task={task} /></span></span>
    <ChevronRight size={17} aria-hidden="true" />
  </button>
}
