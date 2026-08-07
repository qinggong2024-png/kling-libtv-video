import type { WaveSpeedConfig } from './types'

export const WAVESPEED_CONFIG_DEFAULTS = {
  baseUrl: 'https://api.wavespeed.ai/api/v3',
  maxSubmitConcurrency: 1,
  maxPollConcurrency: 4,
  videoModel: 'kwaivgi/kling-video-o3-pro/reference-to-video',
  videoDuration: 10,
  videoAspectRatio: '9:16',
  videoSound: false,
} as const

export type WaveSpeedConfigDraft = {
  enabled: boolean
  baseUrl: string
  maxSubmitConcurrency: number
  maxPollConcurrency: number
  videoModel: string
  videoDuration: number
  videoAspectRatio: string
  videoSound: boolean
  apiKey: string
  clearApiKey: boolean
}

/** Fills fields absent from WaveSpeed config responses deployed before video support. */
export function normalizeWaveSpeedConfig(config: Partial<WaveSpeedConfig>): WaveSpeedConfig {
  return {
    enabled: config.enabled ?? false,
    apiKeyConfigured: config.apiKeyConfigured ?? false,
    credentialSource: config.credentialSource ?? 'none',
    baseUrl: config.baseUrl ?? WAVESPEED_CONFIG_DEFAULTS.baseUrl,
    maxSubmitConcurrency: config.maxSubmitConcurrency ?? WAVESPEED_CONFIG_DEFAULTS.maxSubmitConcurrency,
    maxPollConcurrency: config.maxPollConcurrency ?? WAVESPEED_CONFIG_DEFAULTS.maxPollConcurrency,
    videoModel: config.videoModel ?? WAVESPEED_CONFIG_DEFAULTS.videoModel,
    videoDuration: config.videoDuration ?? WAVESPEED_CONFIG_DEFAULTS.videoDuration,
    videoAspectRatio: config.videoAspectRatio ?? WAVESPEED_CONFIG_DEFAULTS.videoAspectRatio,
    videoSound: config.videoSound ?? WAVESPEED_CONFIG_DEFAULTS.videoSound,
    provider: config.provider ?? 'wavespeed',
    videoProvider: config.videoProvider ?? 'wavespeed_video',
    videoBackendActive: config.videoBackendActive ?? false,
    status: config.status ?? 'UNKNOWN',
    available: config.available ?? false,
    checkedAt: config.checkedAt ?? null,
    reason: config.reason ?? null,
    updatedAt: config.updatedAt ?? null,
    verificationMode: config.verificationMode ?? 'prediction_read_only_lookup',
    verificationMayGenerateOrCharge: config.verificationMayGenerateOrCharge ?? false,
  }
}

export function createWaveSpeedConfigDraft(config: Partial<WaveSpeedConfig>): WaveSpeedConfigDraft {
  const normalized = normalizeWaveSpeedConfig(config)
  return {
    enabled: normalized.enabled,
    baseUrl: normalized.baseUrl,
    maxSubmitConcurrency: normalized.maxSubmitConcurrency,
    maxPollConcurrency: normalized.maxPollConcurrency,
    videoModel: normalized.videoModel,
    videoDuration: normalized.videoDuration,
    videoAspectRatio: normalized.videoAspectRatio,
    videoSound: normalized.videoSound,
    apiKey: '',
    clearApiKey: false,
  }
}
