import type { KlingConfig, KlingConfigPatch } from './types'

export type KlingConfigDraft = Omit<KlingConfig, 'apiKeyConfigured' | 'provider'> & {
  apiKey: string
  clearApiKey: boolean
}

export const KLING_MODEL_OPTIONS = ['kling-3.0-omni'] as const
export const KLING_ASPECT_RATIO_OPTIONS = ['9:16', '16:9', '1:1'] as const
export const KLING_RESOLUTION_OPTIONS = ['720p', '1080p', '4k'] as const
export const KLING_AUDIO_OPTIONS = [
  { value: 'off', label: '关闭' },
  { value: 'native', label: '原生音频' },
] as const

export function createKlingConfigDraft(config: KlingConfig): KlingConfigDraft {
  return {
    backend: config.backend,
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

export function buildKlingConfigPatch(draft: KlingConfigDraft): KlingConfigPatch {
  const apiKey = draft.apiKey.trim()
  return {
    backend: draft.backend,
    ...(apiKey ? { apiKey } : {}),
    ...(draft.clearApiKey ? { clearApiKey: true } : {}),
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
