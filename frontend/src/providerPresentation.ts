export type GenerationProviderKind = 'libtv' | 'kling'

export type ProviderPresentation = {
  kind: GenerationProviderKind
  displayName: string
  cliLabel: string
  cssClass: string
}

export function generationProviderKind(provider?: string | null): GenerationProviderKind {
  const normalized = provider?.trim().toLowerCase() ?? ''
  return normalized === 'kling' || normalized.startsWith('kling_') ? 'kling' : 'libtv'
}

export function providerPresentation(provider?: string | null): ProviderPresentation {
  const normalized = provider?.trim().toLowerCase() ?? ''
  const klingLabel = normalized.includes('_api')
    ? 'Kling API'
    : normalized.includes('_cli')
      ? 'Kling CLI'
      : '可灵官方 Provider'
  return generationProviderKind(provider) === 'kling'
    ? { kind: 'kling', displayName: '可灵', cliLabel: klingLabel, cssClass: 'provider--kling' }
    : { kind: 'libtv', displayName: 'LibTV', cliLabel: 'LibTV CLI', cssClass: 'provider--libtv' }
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
  const providerLabel = meta.cliLabel
  const labels: Record<string, string> = {
    PREPARING: meta.kind === 'kling'
      ? `${providerLabel}：准备并上传参考图`
      : `${providerLabel}：创建画布与节点`,
    QUEUED: meta.kind === 'kling'
      ? `${providerLabel}：等待提交生成`
      : `${providerLabel}：等待运行画布`,
    GENERATING: meta.kind === 'kling'
      ? `${providerLabel}：可灵云端生成中`
      : `${providerLabel}：画布节点生成中`,
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
    return meta.kind === 'kling' ? `${meta.cliLabel} 素材准备` : 'LibTV CLI 画布准备'
  }
  if (key === 'GENERATION') {
    return meta.kind === 'kling' ? '可灵云端生成' : 'LibTV 画布生成'
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
  if (variant.downloadStatus === 'DOWNLOADING') return `${meta.cliLabel} 已返回结果，正在下载成品`
  if (variant.generationStatus === 'UNKNOWN') {
    return meta.kind === 'kling'
      ? `${meta.cliLabel} 提交或查询结果不确定；禁止自动重投，请用任务 ID 对账`
      : 'LibTV CLI 运行状态不确定；禁止重复执行 --run，请读取画布节点对账'
  }
  if (variant.errorCode) {
    const retryable = variant.retryable ?? variant.providerErrorRetryable
    const retry = retryable === true
      ? '可以重试'
      : retryable === false
        ? '需要人工处理'
        : ''
    return [
      `${meta.cliLabel}：${variant.errorCode}`,
      (variant.errorMessage ?? variant.providerErrorMessage)?.trim(),
      retry,
    ].filter(Boolean).join(' · ')
  }
  if (variant.providerTaskId) {
    return meta.kind === 'kling'
      ? `可灵任务 ${variant.providerTaskId} · ${variant.providerStatus ?? '等待查询'}`
      : `LibTV 任务 ${variant.providerTaskId} · ${variant.providerStatus ?? '等待节点结果'}`
  }
  if (variant.generationStatus === 'PENDING') {
    return meta.kind === 'kling' ? `等待 ${meta.cliLabel} 提交生成` : '等待 LibTV CLI 运行画布'
  }
  return meta.kind === 'kling'
    ? `正在等待 ${meta.cliLabel} 返回生成状态`
    : '正在等待 LibTV CLI 返回画布状态'
}
