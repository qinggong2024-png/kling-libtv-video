export type GenerationProviderKind = 'legacy' | 'kling' | 'wavespeed' | 'bach'

export type ProviderPresentation = {
  kind: GenerationProviderKind
  displayName: string
  displayLabel: string
  cssClass: string
}

export function generationProviderKind(provider?: string | null): GenerationProviderKind {
  const normalized = provider?.trim().toLowerCase() ?? ''
  if (normalized === 'wavespeed' || normalized.startsWith('wavespeed_')) return 'wavespeed'
  if (normalized === 'bach' || normalized.startsWith('bach_')) return 'bach'
  return normalized === 'kling' || normalized.startsWith('kling_') ? 'kling' : 'legacy'
}

export function providerPresentation(provider?: string | null): ProviderPresentation {
  const normalized = provider?.trim().toLowerCase() ?? ''
  if (generationProviderKind(provider) === 'kling') {
    const displayLabel = normalized.includes('_cli') ? '可灵历史任务' : '可灵官方 API'
    return { kind: 'kling', displayName: '可灵', displayLabel, cssClass: 'provider--kling' }
  }
  if (generationProviderKind(provider) === 'wavespeed') {
    return {
      kind: 'wavespeed',
      displayName: 'WaveSpeed',
      displayLabel: 'WaveSpeed 视频 API',
      cssClass: 'provider--wavespeed',
    }
  }
  if (generationProviderKind(provider) === 'bach') {
    return {
      kind: 'bach',
      displayName: 'Bach',
      displayLabel: 'Bach Image-to-Video API',
      cssClass: 'provider--bach',
    }
  }
  return {
    kind: 'legacy',
    displayName: '历史任务',
    displayLabel: '历史生成通道',
    cssClass: 'provider--legacy',
  }
}

const PHASE_PROGRESS: Record<string, number> = {
  DRAFT: 8,
  ANALYZING: 28,
  AWAITING_CONFIRMATION: 45,
  PREPARING: 55,
  QUEUED: 64,
  GENERATING: 78,
  PARTIALLY_DELIVERABLE: 92,
  DELIVERABLE: 100,
  ACTION_REQUIRED: 100,
  CANCELLED: 100,
}

export function providerProgress(phase: string, provider?: string | null) {
  const meta = providerPresentation(provider)
  const providerLabel = meta.displayLabel
  const labels: Record<string, string> = {
    PREPARING: meta.kind !== 'legacy'
      ? `${providerLabel}：准备并上传参考图`
      : `${providerLabel}：准备历史任务素材`,
    QUEUED: meta.kind !== 'legacy'
      ? `${providerLabel}：等待提交生成`
      : `${providerLabel}：等待执行`,
    GENERATING: meta.kind !== 'legacy'
      ? `${providerLabel}：云端生成中`
      : `${providerLabel}：生成中`,
    PARTIALLY_DELIVERABLE: `${providerLabel}：部分结果已返回`,
  }
  return {
    ...meta,
    percent: PHASE_PROGRESS[phase] ?? 50,
    label: labels[phase] ?? null,
  }
}

export function providerTimingStageLabel(key: string, provider?: string | null): string {
  const meta = providerPresentation(provider)
  if (key === 'SOURCE_UPLOAD') return '素材上传'
  if (key === 'ANALYSIS') return '内容分析'
  if (key === 'CONFIRMATION') return '方案确认'
  if (key === 'MATERIALIZATION') {
    return meta.kind !== 'legacy' ? `${meta.displayLabel} 素材准备` : '历史任务素材准备'
  }
  if (key === 'GENERATION') {
    return meta.kind === 'wavespeed'
      ? 'WaveSpeed 云端生成'
      : meta.kind === 'bach'
        ? 'Bach 云端生成'
        : meta.kind === 'kling' ? '可灵云端生成' : '历史任务生成'
  }
  return '成品下载'
}

type VariantExecution = {
  generationStatus: string
  downloadStatus: string
  downloadArtifactId: string | null
  errorCode: string | null
  provider?: string | null
  providerTaskId?: string | null
  providerStatus?: string | null
  errorMessage?: string | null
  retryable?: boolean | null
  providerErrorMessage?: string | null
  providerErrorRetryable?: boolean | null
}

export function variantExecutionMessage(
  variant: VariantExecution,
  taskProvider?: string | null,
): string {
  const meta = providerPresentation(variant.provider ?? taskProvider)
  if (variant.downloadArtifactId) return '成品文件已就绪'
  if (variant.downloadStatus === 'DOWNLOADING') return `${meta.displayLabel} 已返回结果，正在下载成品`
  if (variant.generationStatus === 'UNKNOWN') {
    return meta.kind !== 'legacy'
      ? `${meta.displayLabel} 提交或查询结果不确定；禁止自动重投，请用任务 ID 对账`
      : '历史任务执行状态不确定；禁止重复提交，请根据任务记录对账'
  }
  if (variant.errorCode) {
    const retryable = variant.retryable ?? variant.providerErrorRetryable
    const retry = retryable === true
      ? '可以重试'
      : retryable === false
        ? '需要人工处理'
        : ''
    return [
      `${meta.displayLabel}：${variant.errorCode}`,
      (variant.errorMessage ?? variant.providerErrorMessage)?.trim(),
      retry,
    ].filter(Boolean).join(' · ')
  }
  if (variant.providerTaskId) {
    return meta.kind !== 'legacy'
      ? `${meta.displayName} 任务 ${variant.providerTaskId} · ${variant.providerStatus ?? '等待查询'}`
      : `历史任务 ${variant.providerTaskId} · ${variant.providerStatus ?? '等待结果'}`
  }
  if (variant.generationStatus === 'PENDING') {
    return meta.kind !== 'legacy' ? `等待 ${meta.displayLabel} 提交生成` : '等待历史任务执行'
  }
  return meta.kind !== 'legacy'
    ? `正在等待 ${meta.displayLabel} 返回生成状态`
    : '正在等待历史任务返回状态'
}
