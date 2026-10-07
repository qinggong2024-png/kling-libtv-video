import type { Task, Variant } from '../types'
import type { StatusTone } from '../types'
import { ANALYSIS_FAILURE_CODES, statusMeta } from './workflowStates'

export type StatusSource = 'task' | 'attempt' | 'image'
export type StatusSemantic =
  | 'processing'
  | 'completed'
  | 'partial'
  | 'failed'
  | 'unknown'
  | 'manual'
  | 'confirmation'
  | 'cancelled'

export type StatusAction =
  | 'NONE'
  | 'CONFIRM'
  | 'REVIEW'
  | 'RETRY'
  | 'RECONCILE'
  | 'REFRESH'
  | 'DOWNLOAD'
  | 'REGENERATE'

export type StatusPresentation = {
  semantic: StatusSemantic
  label: string
  tone: StatusTone
  actions: readonly StatusAction[]
  primaryAction: StatusAction | null
  actionLabel: string | null
  description: string
}

export type StatusPresentationInput = {
  source: StatusSource
  value: string | null | undefined
  reasonCode?: string | null
  retryable?: boolean | null
  canConfirm?: boolean
  canDownload?: boolean
  hasArtifact?: boolean
}

const NONE_ACTION = ['NONE'] as const

const PROCESSING: Omit<StatusPresentation, 'label'> = {
  semantic: 'processing',
  tone: 'active',
  actions: NONE_ACTION,
  primaryAction: null,
  actionLabel: null,
  description: '任务正在处理中，系统会继续推进并更新状态。',
}

const COMPLETED: Omit<StatusPresentation, 'label'> = {
  semantic: 'completed',
  tone: 'success',
  actions: ['DOWNLOAD'],
  primaryAction: 'DOWNLOAD',
  actionLabel: '下载成品',
  description: '任务已完成，可以查看或下载成品。',
}

const PARTIAL: Omit<StatusPresentation, 'label'> = {
  semantic: 'partial',
  tone: 'warning',
  actions: ['REVIEW'],
  primaryAction: 'REVIEW',
  actionLabel: '查看结果',
  description: '部分结果已完成，请查看已完成内容并处理剩余项目。',
}

const FAILED: Omit<StatusPresentation, 'label'> = {
  semantic: 'failed',
  tone: 'danger',
  actions: ['REVIEW'],
  primaryAction: 'REVIEW',
  actionLabel: '查看原因',
  description: '任务未能完成，请查看失败原因后决定是否重试。',
}

const UNKNOWN: Omit<StatusPresentation, 'label'> = {
  semantic: 'unknown',
  tone: 'warning',
  actions: ['RECONCILE'],
  primaryAction: 'RECONCILE',
  actionLabel: '核对状态',
  description: '当前结果不确定，请先查询或对账，确认前不要重复提交。',
}

const MANUAL: Omit<StatusPresentation, 'label'> = {
  semantic: 'manual',
  tone: 'danger',
  actions: ['REVIEW'],
  primaryAction: 'REVIEW',
  actionLabel: '人工处理',
  description: '任务需要人工处理，请查看原因并按提示完成下一步。',
}

const CONFIRMATION: Omit<StatusPresentation, 'label'> = {
  semantic: 'confirmation',
  tone: 'warning',
  actions: ['CONFIRM'],
  primaryAction: 'CONFIRM',
  actionLabel: '确认方案',
  description: '任务正在等待确认，确认后才会继续生成。',
}

const CANCELLED: Omit<StatusPresentation, 'label'> = {
  semantic: 'cancelled',
  tone: 'neutral',
  actions: NONE_ACTION,
  primaryAction: null,
  actionLabel: null,
  description: '任务已取消，不会继续推进。',
}

const TASK_SEMANTICS: Record<string, Omit<StatusPresentation, 'label'>> = {
  DRAFT: PROCESSING,
  ANALYZING: PROCESSING,
  AWAITING_CONFIRMATION: CONFIRMATION,
  PREPARING: PROCESSING,
  WAITING_FOR_SEAL: PROCESSING,
  QUEUED: PROCESSING,
  GENERATING: PROCESSING,
  DOWNLOADING: PROCESSING,
  VALIDATING: PROCESSING,
  AWAITING_FINAL_APPROVAL: { ...CONFIRMATION, actionLabel: '审核结果', description: '结果已生成，等待人工审核后才能完成交付。' },
  PARTIALLY_DELIVERABLE: PARTIAL,
  DELIVERABLE: COMPLETED,
  ACTION_REQUIRED: MANUAL,
  CANCELLED,
}

const ATTEMPT_SEMANTICS: Record<string, Omit<StatusPresentation, 'label'>> = {
  SUCCEEDED: COMPLETED,
  PARTIAL,
  RUNNING: PROCESSING,
  PENDING: PROCESSING,
  FAILED,
  UNKNOWN,
  READY: { ...COMPLETED, actionLabel: '下载成品' },
}

const IMAGE_SEMANTICS: Record<string, Omit<StatusPresentation, 'label'>> = {
  uploading: PROCESSING,
  submitting: PROCESSING,
  queued: PROCESSING,
  running: PROCESSING,
  completed: COMPLETED,
  failed: FAILED,
  write_uncertain: UNKNOWN,
}

const IMAGE_STATUS_LABELS: Record<string, string> = {
  uploading: '上传素材',
  submitting: '正在提交',
  queued: '排队中',
  running: '正在生成图片',
  completed: '已完成',
  failed: '生成失败',
  write_uncertain: '提交待确认',
}

function actionState(
  base: Omit<StatusPresentation, 'label'>,
  input: StatusPresentationInput,
): Omit<StatusPresentation, 'label'> {
  if (base.semantic === 'completed' && (input.canDownload === false || input.hasArtifact === false)) {
    return { ...base, actions: NONE_ACTION, primaryAction: null, actionLabel: null }
  }
  if (base.semantic === 'confirmation' && input.canConfirm === false) {
    return { ...base, actions: ['REVIEW'], primaryAction: 'REVIEW', actionLabel: '查看方案' }
  }
  if (base.semantic === 'failed' && input.retryable === true) {
    return { ...base, actions: ['RETRY'], primaryAction: 'RETRY', actionLabel: '重试任务' }
  }
  if (base.semantic === 'failed' && input.retryable === false) {
    return { ...base, actions: ['REVIEW'], primaryAction: 'REVIEW', actionLabel: '人工处理', description: '任务失败且不能安全自动重试，请人工核对原因后处理。' }
  }
  return base
}

function defaultLabel(source: StatusSource, value: string): string {
  if (source === 'task' || source === 'attempt') return statusMeta[value]?.label ?? '状态待确认'
  return IMAGE_STATUS_LABELS[value] ?? '状态待确认'
}

function normalizedValue(source: StatusSource, value: string): string {
  return source === 'image' ? value.toLowerCase() : value.toUpperCase()
}

/**
 * 将后端或本地任务状态翻译为统一的用户语义。
 *
 * `value` 始终保留原始业务状态值，未知值只影响展示，不会被重写或猜测成别的业务状态。
 */
export function statusPresentation(input: StatusPresentationInput): StatusPresentation {
  const value = input.value?.trim() ?? ''
  const key = normalizedValue(input.source, value)
  const semantic = input.source === 'task'
    ? TASK_SEMANTICS[key]
    : input.source === 'attempt'
      ? ATTEMPT_SEMANTICS[key]
      : IMAGE_SEMANTICS[key]

  if (!semantic) {
    return {
      ...actionState(UNKNOWN, input),
      label: '状态待确认',
    }
  }

  return {
    ...actionState(semantic, input),
    label: defaultLabel(input.source, key),
  }
}

const ANALYSIS_FAILURE_LABELS: Record<string, string> = {
  ANALYSIS_TIMEOUT: '方案分析超时',
  ANALYSIS_CANCELLED: '方案分析中断',
  ANALYSIS_PROVIDER_FAILED: '分析服务异常',
  ANALYSIS_STALE_RECOVERED: '方案分析待重试',
  ANALYSIS_SCHEMA_INVALID: '方案数据异常',
}

export function taskStatusPresentation(task: Task): StatusPresentation {
  const base = statusPresentation({
    source: 'task',
    value: task.phase,
    reasonCode: task.phaseReasonCode,
    canConfirm: task.actionCapabilities.canConfirm,
    canDownload: task.actionCapabilities.canDownload,
  })

  if (task.phase === 'ACTION_REQUIRED' && ANALYSIS_FAILURE_CODES.has(task.phaseReasonCode ?? '')) {
    const failure = actionState(FAILED, {
      source: 'task',
      value: task.phase,
      retryable: task.actionCapabilities.canRetryAnalysis,
    })
    return {
      ...failure,
      label: ANALYSIS_FAILURE_LABELS[task.phaseReasonCode ?? ''] ?? '方案分析未完成',
      description: '方案分析未完成，请检查素材或服务状态后重新分析。',
    }
  }

  return base
}

export function attemptStatusPresentation(variant: Pick<Variant, 'generationStatus' | 'retryable' | 'providerErrorRetryable' | 'downloadArtifactId'>): StatusPresentation {
  return statusPresentation({
    source: 'attempt',
    value: variant.generationStatus,
    retryable: variant.retryable ?? variant.providerErrorRetryable,
    hasArtifact: Boolean(variant.downloadArtifactId),
  })
}

export function imageStatusPresentation(
  value: string | null | undefined,
  options: Pick<StatusPresentationInput, 'retryable'> = {},
): StatusPresentation {
  return statusPresentation({ source: 'image', value, ...options })
}
