// 本文件由 App.tsx 拆分生成（2026-09-28 前端架构拆分 v2）。
// 代码为逐字搬运，未经逻辑改写。
import { type StatusTone, type Task, type Variant, type VariantKind } from '../types'
import { parseTaskTimestamp } from '../taskTiming'
import { providerActionRequiredMessage } from '../providerPresentation'
import { ANALYSIS_FAILURE_CODES, statusMeta } from './workflowStates'

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

export function formatTime(value: string) {
  return new Date(parseTaskTimestamp(value)).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

export function isAnalysisFailure(task: Task): boolean {
  return task.phase === 'ACTION_REQUIRED' && ANALYSIS_FAILURE_CODES.has(task.phaseReasonCode ?? '')
}

export function taskStatus(task: Task): { label: string; tone: StatusTone } {
  if (!isAnalysisFailure(task)) {
    const meta = statusMeta[task.phase]
    if (meta) return meta
    // 后端新增 phase 时不要直接把原始枚举渲染给用户，补映射前先给安全兜底。
    console.warn(`[taskStatus] 缺少中文标签映射：phase=${task.phase}，请在 statusMeta 中补充`)
    return { label: '状态待确认', tone: 'warning' }
  }
  const labels: Record<string, string> = {
    ANALYSIS_TIMEOUT: '方案分析超时',
    ANALYSIS_CANCELLED: '方案分析中断',
    ANALYSIS_PROVIDER_FAILED: '分析服务异常',
    ANALYSIS_STALE_RECOVERED: '方案分析待重试',
    ANALYSIS_SCHEMA_INVALID: '方案数据异常',
  }
  return { label: labels[task.phaseReasonCode ?? ''] ?? '方案分析未完成', tone: 'danger' }
}

export function taskFailureMessage(task: Task): string {
  const messages: Record<string, string> = {
    ANALYSIS_TIMEOUT: '素材较多或分析服务耗时较长，已达到本次按素材数量计算的等待上限。',
    ANALYSIS_CANCELLED: '上一次后台分析意外中断，素材仍然保留。',
    ANALYSIS_PROVIDER_FAILED: '分析服务暂时没有返回有效结果，素材仍然保留。',
    ANALYSIS_STALE_RECOVERED: '系统检测到后台分析长时间没有更新，已停止等待旧任务。',
    ANALYSIS_SCHEMA_INVALID: '分析结果不完整，无法生成可确认的视频方案。',
  }
  return messages[task.phaseReasonCode ?? '']
    ?? providerActionRequiredMessage(task.phaseReasonCode, task.generationProvider)
}
