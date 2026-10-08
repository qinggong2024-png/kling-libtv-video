import type { Task } from '../types'
import { attemptStatusPresentation, taskStatusPresentation } from './statusPresentation'

export type TaskStatus = 'queued' | 'preparing' | 'running' | 'validation' | 'completed' | 'failed'

const phaseStatus: Record<string, TaskStatus> = {
  DRAFT: 'preparing',
  ANALYZING: 'preparing',
  PREPARING: 'preparing',
  WAITING_FOR_SEAL: 'preparing',
  QUEUED: 'queued',
  GENERATING: 'running',
  DOWNLOADING: 'validation',
  VALIDATING: 'validation',
  DELIVERABLE: 'completed',
  ACTION_REQUIRED: 'failed',
}

export function studioTaskPresentation(task: Task) {
  // Uncertain attempts keep their real label and never acquire a normal completion state.
  const unknown = task.variants.find((variant) => variant.generationStatus === 'UNKNOWN')
  if (unknown) return { ...attemptStatusPresentation(unknown), status: null }
  return { ...taskStatusPresentation(task), status: phaseStatus[task.phase] ?? null }
}
