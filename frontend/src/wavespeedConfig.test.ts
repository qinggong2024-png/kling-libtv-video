import { describe, expect, it } from 'vitest'

import {
  createWaveSpeedConfigDraft,
  normalizeWaveSpeedConfig,
  WAVESPEED_CONFIG_DEFAULTS,
} from './wavespeedConfig'

describe('WaveSpeed provider configuration', () => {
  it('normalizes config responses deployed before video settings were added', () => {
    const legacyResponse = {
      enabled: true,
      apiKeyConfigured: true,
      credentialSource: 'admin' as const,
      baseUrl: 'https://api.wavespeed.ai/api/v3',
      status: 'READY',
      available: true,
      checkedAt: null,
    }

    const config = normalizeWaveSpeedConfig(legacyResponse)
    const draft = createWaveSpeedConfigDraft(legacyResponse)

    expect(config).toMatchObject({
      ...WAVESPEED_CONFIG_DEFAULTS,
      enabled: true,
      apiKeyConfigured: true,
      credentialSource: 'admin',
      status: 'READY',
      available: true,
    })
    expect(draft).toMatchObject(WAVESPEED_CONFIG_DEFAULTS)
    expect(draft.baseUrl.trim()).toBe(WAVESPEED_CONFIG_DEFAULTS.baseUrl)
    expect(draft.videoModel.trim()).toBe(WAVESPEED_CONFIG_DEFAULTS.videoModel)
    expect(draft.apiKey.trim()).toBe('')
  })

  it('preserves explicit video settings from current responses', () => {
    const config = normalizeWaveSpeedConfig({
      videoModel: 'custom/model',
      videoDuration: 5,
      videoAspectRatio: '16:9',
      videoSound: true,
    })

    expect(config).toMatchObject({
      videoModel: 'custom/model',
      videoDuration: 5,
      videoAspectRatio: '16:9',
      videoSound: true,
    })
  })
})
