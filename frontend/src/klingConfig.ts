import type { KlingConfig, KlingConfigPatch } from './types'

export type KlingConfigDraft = Omit<KlingConfig, 'apiKeyConfigured' | 'provider' | 'callbackUrl'> & {
  apiKey: string
  clearApiKey: boolean
  callbackUrl: string
}

export const KLING_MODEL_OPTIONS = ['kling-3.0-omni'] as const
export const KLING_BASE_URL_OPTIONS = [
  'https://api-beijing.klingai.com',
  'https://api-singapore.klingai.com',
] as const
export const KLING_ASPECT_RATIO_OPTIONS = ['9:16', '16:9', '1:1'] as const
export const KLING_RESOLUTION_OPTIONS = ['720p', '1080p', '4k'] as const
export const KLING_AUDIO_OPTIONS = [
  { value: 'off', label: '关闭' },
  { value: 'native', label: '原生音频' },
  { value: 'original', label: '保留参考视频原声' },
] as const

export type KlingApiStatusPresentation = {
  label: string
  message: string
  tone: 'success' | 'warning' | 'danger' | 'neutral'
}

const KLING_API_STATUS_PRESENTATIONS: Record<string, KlingApiStatusPresentation> = {
  KLING_API_READY: {
    label: '已就绪',
    message: '官方 API 鉴权与只读能力验证均已通过。',
    tone: 'success',
  },
  KLING_API_CONFIGURED_UNVERIFIED: {
    label: '待验证',
    message: 'API Key 已保存，等待执行只读任务查询验证。',
    tone: 'warning',
  },
  KLING_API_AUTHENTICATION_FAILED: {
    label: '鉴权失败',
    message: 'API Key 无效或已失效，请更新密钥后重新验证。',
    tone: 'danger',
  },
  KLING_API_VERIFICATION_FAILED: {
    label: '验证失败',
    message: '官方 API 暂时无法完成只读验证，请检查网络、区域与服务状态。',
    tone: 'danger',
  },
  KLING_API_KEY_MISSING: {
    label: '缺少密钥',
    message: '尚未配置可灵官方 API Key。',
    tone: 'warning',
  },
  KLING_API_DISABLED: {
    label: '未启用',
    message: '官方 API 通道已关闭，新任务不会提交到可灵。',
    tone: 'neutral',
  },
}

export function klingApiStatusPresentation(
  status: string | undefined,
  enabled = false,
  reason?: string | null,
): KlingApiStatusPresentation {
  if (status && KLING_API_STATUS_PRESENTATIONS[status]) {
    return KLING_API_STATUS_PRESENTATIONS[status]
  }
  return enabled
    ? {
        label: '能力不可用',
        message: reason || '官方 API 当前不可用，请刷新验证状态。',
        tone: 'danger',
      }
    : KLING_API_STATUS_PRESENTATIONS.KLING_API_DISABLED
}

export function formatKlingApiVersion(value?: string | null): string {
  if (!value) return ''
  const normalized = value.trim()
  return normalized.toLowerCase().startsWith('api-')
    ? `API ${normalized.slice(4)}`
    : normalized
}

export function createKlingConfigDraft(config: KlingConfig): KlingConfigDraft {
  return {
    backend: config.backend,
    baseUrl: config.baseUrl ?? '',
    callbackUrl: config.callbackUrl ?? '',
    model: config.model,
    duration: config.duration,
    aspectRatio: config.aspectRatio,
    resolution: config.resolution,
    audio: config.audio,
    multiShot: config.multiShot,
    maxSubmitConcurrency: config.maxSubmitConcurrency,
    maxPollConcurrency: config.maxPollConcurrency,
    enabled: config.enabled,
    apiKey: '',
    clearApiKey: false,
  }
}

export function validateKlingConfig(
  draft: KlingConfigDraft,
  apiKeyConfigured: boolean,
): string {
  const willHaveApiKey = Boolean(draft.apiKey.trim()) || (apiKeyConfigured && !draft.clearApiKey)
  if (draft.backend === 'api' && draft.enabled && !willHaveApiKey) {
    return '启用可灵官方 API 前，请先配置 API Key。'
  }
  const normalizedBaseUrl = draft.baseUrl.trim().replace(/\/+$/, '')
  if (!KLING_BASE_URL_OPTIONS.some((value) => value === normalizedBaseUrl)) {
    return 'API Base URL 必须选择可灵北京或新加坡官方端点。'
  }
  if (!validCallbackUrl(draft.callbackUrl)) {
    return '回调 URL 必须是无账号信息和片段的有效 HTTPS 地址。'
  }
  if (!Number.isInteger(draft.duration) || draft.duration < 3 || draft.duration > 15) {
    return '视频时长必须是 3–15 秒之间的整数。'
  }
  if (!Number.isInteger(draft.maxSubmitConcurrency) || draft.maxSubmitConcurrency < 1 || draft.maxSubmitConcurrency > 20) {
    return '提交并发必须是 1–20 之间的整数。'
  }
  if (!Number.isInteger(draft.maxPollConcurrency) || draft.maxPollConcurrency < 1 || draft.maxPollConcurrency > 50) {
    return '查询并发必须是 1–50 之间的整数。'
  }
  return ''
}

function validCallbackUrl(value: string): boolean {
  const normalized = value.trim()
  if (!normalized) return true
  try {
    const url = new URL(normalized)
    return url.protocol === 'https:'
      && !url.username
      && !url.password
      && !url.hash
  } catch {
    return false
  }
}

export function buildKlingConfigPatch(draft: KlingConfigDraft): KlingConfigPatch {
  const apiKey = draft.apiKey.trim()
  return {
    ...(apiKey ? { apiKey } : {}),
    ...(draft.clearApiKey ? { clearApiKey: true } : {}),
    baseUrl: draft.baseUrl.trim().replace(/\/+$/, ''),
    ...(draft.callbackUrl.trim()
      ? { callbackUrl: draft.callbackUrl.trim() }
      : { clearCallbackUrl: true }),
    model: draft.model,
    duration: draft.duration,
    aspectRatio: draft.aspectRatio,
    resolution: draft.resolution,
    audio: draft.audio,
    multiShot: draft.multiShot,
    maxSubmitConcurrency: draft.maxSubmitConcurrency,
    maxPollConcurrency: draft.maxPollConcurrency,
    enabled: draft.enabled,
  }
}
