const EXPLICIT_TIMEZONE = /(Z|[+-]\d{2}:\d{2})$/i

export type TaskTimingStageKey =
  | 'SOURCE_UPLOAD'
  | 'ANALYSIS'
  | 'CONFIRMATION'
  | 'MATERIALIZATION'
  | 'GENERATION'
  | 'DOWNLOAD'

export type ProductionStageKey =
  | 'MATERIALS'
  | 'TEMPLATE'
  | 'PREFLIGHT'
  | 'ANALYSIS'
  | 'PLAN'
  | 'GENERATION'
  | 'RESULT'

const FIXED_TEMPLATE_STAGE_KEYS: readonly TaskTimingStageKey[] = [
  'SOURCE_UPLOAD',
  'GENERATION',
  'DOWNLOAD',
]

const LEGACY_ANALYSIS_STAGE_KEYS: readonly TaskTimingStageKey[] = [
  'SOURCE_UPLOAD',
  'ANALYSIS',
  'CONFIRMATION',
  'MATERIALIZATION',
  'GENERATION',
  'DOWNLOAD',
]

const CUSTOM_PRODUCTION_STAGE_KEYS: readonly ProductionStageKey[] = [
  'MATERIALS',
  'GENERATION',
  'RESULT',
]

const FIXED_TEMPLATE_PRODUCTION_STAGE_KEYS: readonly ProductionStageKey[] = [
  'MATERIALS',
  'TEMPLATE',
  'PREFLIGHT',
  'GENERATION',
  'RESULT',
]

const LEGACY_PRODUCTION_STAGE_KEYS: readonly ProductionStageKey[] = [
  'MATERIALS',
  'ANALYSIS',
  'PLAN',
  'GENERATION',
  'RESULT',
]

export function visibleTaskTimingStageKeys(
  workflowKind?: string | null,
): readonly TaskTimingStageKey[] {
  return workflowKind === 'FIXED_TEMPLATE'
    ? FIXED_TEMPLATE_STAGE_KEYS
    : LEGACY_ANALYSIS_STAGE_KEYS
}

export function visibleProductionStageKeys(
  workflowKind?: string | null,
  generationMode?: unknown,
): readonly ProductionStageKey[] {
  if (workflowKind !== 'FIXED_TEMPLATE') return LEGACY_PRODUCTION_STAGE_KEYS
  return generationMode === 'custom'
    ? CUSTOM_PRODUCTION_STAGE_KEYS
    : FIXED_TEMPLATE_PRODUCTION_STAGE_KEYS
}

export function currentProductionStageIndex(
  phase: string,
  workflowKind?: string | null,
  generationMode?: unknown,
): number {
  const stages = visibleProductionStageKeys(workflowKind, generationMode)
  if (phase === 'DRAFT') return 0
  if (phase === 'DELIVERABLE' || phase === 'PARTIALLY_DELIVERABLE') return stages.length - 1

  if (workflowKind === 'FIXED_TEMPLATE') {
    if (generationMode === 'custom') return 1
    return phase === 'PREPARING' ? 2 : 3
  }

  if (phase === 'ANALYZING' || phase === 'ACTION_REQUIRED') return 1
  if (phase === 'AWAITING_CONFIRMATION') return 2
  return 3
}

export function parseTaskTimestamp(value: string): number {
  const normalized = EXPLICIT_TIMEZONE.test(value) ? value : `${value}Z`
  return new Date(normalized).getTime()
}

export function formatElapsed(value: string, endValue: string | number = Date.now()): string {
  const startTime = parseTaskTimestamp(value)
  const endTime = typeof endValue === 'number' ? endValue : parseTaskTimestamp(endValue)
  if (!Number.isFinite(startTime) || !Number.isFinite(endTime)) return '—'

  const seconds = Math.max(0, Math.floor((endTime - startTime) / 1000))
  if (seconds < 60) return `${seconds} 秒`
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟`

  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  return minutes ? `${hours} 小时 ${minutes} 分钟` : `${hours} 小时`
}

export function formatDurationSeconds(value: number): string {
  const seconds = Math.max(0, Math.floor(value))
  if (seconds < 60) return `${seconds} 秒`
  if (seconds < 3600) {
    const minutes = Math.floor(seconds / 60)
    const remainder = seconds % 60
    return remainder ? `${minutes} 分 ${remainder} 秒` : `${minutes} 分钟`
  }

  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  return minutes ? `${hours} 小时 ${minutes} 分` : `${hours} 小时`
}
