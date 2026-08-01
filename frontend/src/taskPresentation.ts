import type { StatusTone, Task, Variant, VariantKind } from './types'

export const ACTIVE_PHASES = new Set(['DRAFT', 'ANALYZING', 'PREPARING', 'WAITING_FOR_SEAL', 'QUEUED', 'GENERATING', 'DOWNLOADING', 'VALIDATING'])
export const RESULT_PHASES = new Set(['DELIVERABLE', 'PARTIALLY_DELIVERABLE'])
export const COMPLETED_PHASES = new Set(['DELIVERABLE'])
export const TERMINAL_PHASES = new Set(['DELIVERABLE', 'PARTIALLY_DELIVERABLE', 'ACTION_REQUIRED', 'CANCELLED'])
export const FAILED_PHASES = new Set(['ACTION_REQUIRED'])

const ANALYSIS_FAILURE_CODES = new Set([
  'ANALYSIS_TIMEOUT',
  'ANALYSIS_CANCELLED',
  'ANALYSIS_PROVIDER_FAILED',
  'ANALYSIS_STALE_RECOVERED',
  'ANALYSIS_SCHEMA_INVALID',
])

export const analysisStageLabels: Record<string, string> = {
  QUEUED: '等待后台分析',
  PREPARING_IMAGES: '正在准备图片',
  PROVIDER_RUNNING: '大模型正在分析素材',
  VALIDATING: '正在校验视频方案',
}

const statusMeta: Record<string, { label: string; tone: StatusTone }> = {
  DRAFT: { label: '正在上传素材', tone: 'neutral' },
  ANALYZING: { label: '正在分析图片', tone: 'active' },
  AWAITING_CONFIRMATION: { label: '等待确认方案', tone: 'warning' },
  PREPARING: { label: '正在准备生成', tone: 'active' },
  WAITING_FOR_SEAL: { label: '正在锁定生成任务', tone: 'active' },
  QUEUED: { label: '等待生成', tone: 'active' },
  GENERATING: { label: '正在生成视频', tone: 'active' },
  DOWNLOADING: { label: '正在下载成品', tone: 'active' },
  VALIDATING: { label: '正在校验成品', tone: 'active' },
  PARTIALLY_DELIVERABLE: { label: '部分完成', tone: 'warning' },
  DELIVERABLE: { label: '已完成', tone: 'success' },
  ACTION_REQUIRED: { label: '任务需要处理', tone: 'danger' },
  CANCELLED: { label: '已取消', tone: 'neutral' },
  SUCCEEDED: { label: '已完成', tone: 'success' },
  PARTIAL: { label: '部分完成', tone: 'warning' },
  RUNNING: { label: '正在生成视频', tone: 'active' },
  PENDING: { label: '等待生成', tone: 'neutral' },
  FAILED: { label: '生成失败', tone: 'danger' },
  UNKNOWN: { label: '状态待确认', tone: 'warning' },
  READY: { label: '可下载', tone: 'success' },
}

const ANALYSIS_FAILURE_LABELS: Record<string, string> = {
  ANALYSIS_TIMEOUT: '方案分析超时',
  ANALYSIS_CANCELLED: '方案分析中断',
  ANALYSIS_PROVIDER_FAILED: '分析服务异常',
  ANALYSIS_STALE_RECOVERED: '方案分析待重试',
  ANALYSIS_SCHEMA_INVALID: '方案数据异常',
}

const ANALYSIS_FAILURE_MESSAGES: Record<string, string> = {
  ANALYSIS_TIMEOUT: '素材较多或分析服务耗时较长，已达到本次按素材数量计算的等待上限。',
  ANALYSIS_CANCELLED: '上一次后台分析意外中断，素材仍然保留。',
  ANALYSIS_PROVIDER_FAILED: '分析服务暂时没有返回有效结果，素材仍然保留。',
  ANALYSIS_STALE_RECOVERED: '系统检测到后台分析长时间没有更新，已停止等待旧任务。',
  ANALYSIS_SCHEMA_INVALID: '分析结果不完整，无法生成可确认的视频方案。',
}

export function taskPrompt(task: Task, kind: VariantKind): string {
  return task.variants.find((variant) => variant.kind === kind)?.promptText
    ?? task.variants[0]?.promptText
    ?? ''
}

export function validateCompatibleBaseUrl(value: string): string {
  const normalized = value.trim()
  if (!normalized) return ''
  try {
    const url = new URL(normalized)
    const loopback = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)
    if (url.protocol !== 'https:' && !(url.protocol === 'http:' && loopback)) return '请使用 HTTPS；仅本机地址允许 HTTP。'
    if (url.username || url.password || url.search || url.hash) return '地址不能包含账号密码、查询参数或片段。'
  } catch { return '请输入完整地址，例如 https://gateway.example.com/v1。' }
  return ''
}

export function variantKindShortLabel(kind: VariantKind) {
  return kind === 'STABLE' ? '稳' : '动'
}

export function variantKindDisplayName(kind: VariantKind) {
  return kind === 'STABLE' ? '稳定展示' : '动态广告'
}

export function variantShortLabel(variant: Variant) {
  return variant.variantIndex ? String(variant.variantIndex) : variantKindShortLabel(variant.kind)
}

export function variantDisplayName(variant: Variant) {
  return variant.variantIndex ? `结果 ${variant.variantIndex}` : variantKindDisplayName(variant.kind)
}

export function variantLabelClass(variant: Variant) {
  return variant.variantIndex ? 'variant-label--result' : variant.kind === 'STABLE' ? 'variant-label--a' : 'variant-label--b'
}

export function variantFileToken(variant: Variant) {
  return variant.variantKey ?? variant.kind.toLowerCase()
}

export function variantErrorMessage(variant: Variant) {
  return variant.errorMessage ?? variant.providerErrorMessage ?? null
}

export function variantErrorRetryable(variant: Variant) {
  return variant.retryable ?? variant.providerErrorRetryable ?? null
}

export function variantErrorDetails(variant: Variant) {
  return variant.errorDetails ?? variant.providerErrorDetails ?? null
}

export function statusPresentation(value: string): { label: string; tone: StatusTone } {
  return statusMeta[value] ?? { label: value, tone: 'neutral' }
}

export function isAnalysisFailure(task: Pick<Task, 'phase' | 'phaseReasonCode'>): boolean {
  return task.phase === 'ACTION_REQUIRED' && ANALYSIS_FAILURE_CODES.has(task.phaseReasonCode ?? '')
}

export function taskStatus(task: Pick<Task, 'phase' | 'phaseReasonCode'>): { label: string; tone: StatusTone } {
  if (!isAnalysisFailure(task)) return statusPresentation(task.phase)
  return { label: ANALYSIS_FAILURE_LABELS[task.phaseReasonCode ?? ''] ?? '方案分析未完成', tone: 'danger' }
}

export function taskFailureMessage(task: Pick<Task, 'phaseReasonCode'>): string {
  return ANALYSIS_FAILURE_MESSAGES[task.phaseReasonCode ?? ''] ?? '任务遇到问题，需要查看技术信息后处理。'
}
