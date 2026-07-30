import { describe, expect, it } from 'vitest'
import {
  buildKlingConfigPatch,
  createKlingConfigDraft,
  formatKlingApiVersion,
  klingApiStatusPresentation,
  KLING_AUDIO_OPTIONS,
  validateKlingConfig,
} from './klingConfig'
import type { KlingConfig } from './types'

const config: KlingConfig = {
  backend: 'api',
  apiKeyConfigured: false,
  baseUrl: 'https://api-beijing.klingai.com',
  callbackUrl: null,
  model: 'kling-3.0-omni',
  duration: 10,
  aspectRatio: '9:16',
  resolution: '1080p',
  audio: 'off',
  multiShot: true,
  maxSubmitConcurrency: 1,
  maxPollConcurrency: 4,
  enabled: true,
  provider: 'kling_official_api',
}

describe('Kling provider configuration', () => {
  it('offers every official Omni audio mode', () => {
    expect(KLING_AUDIO_OPTIONS.map((option) => option.value)).toEqual([
      'off',
      'native',
      'original',
    ])
  })

  it('never places the saved API key in the editable draft', () => {
    const draft = createKlingConfigDraft({ ...config, apiKeyConfigured: true })

    expect(draft.apiKey).toBe('')
    expect(draft.clearApiKey).toBe(false)
  })

  it('blocks an enabled API provider until a key is available', () => {
    const draft = createKlingConfigDraft(config)

    expect(validateKlingConfig(draft, false)).toBe('启用可灵官方 API 前，请先配置 API Key。')
    expect(validateKlingConfig({ ...draft, apiKey: 'new-secret-key' }, false)).toBe('')
    expect(validateKlingConfig(draft, true)).toBe('')
    expect(validateKlingConfig({ ...draft, clearApiKey: true }, true)).toBe('启用可灵官方 API 前，请先配置 API Key。')
  })

  it('keeps an existing key by omission and sends explicit replacement or clearing', () => {
    const draft = createKlingConfigDraft({ ...config, apiKeyConfigured: true })

    expect(buildKlingConfigPatch(draft)).not.toHaveProperty('apiKey')
    expect(buildKlingConfigPatch(draft)).not.toHaveProperty('clearApiKey')
    expect(buildKlingConfigPatch({ ...draft, apiKey: ' replacement-key ' })).toMatchObject({
      apiKey: 'replacement-key',
    })
    expect(buildKlingConfigPatch({ ...draft, clearApiKey: true })).toMatchObject({
      clearApiKey: true,
    })
  })

  it('validates submit and query concurrency limits', () => {
    const draft = createKlingConfigDraft({ ...config, apiKeyConfigured: true })

    expect(validateKlingConfig({ ...draft, duration: 2 }, true)).toContain('3–15')
    expect(validateKlingConfig({ ...draft, duration: 16 }, true)).toContain('3–15')
    expect(validateKlingConfig({ ...draft, maxSubmitConcurrency: 0 }, true)).toContain('1–20')
    expect(validateKlingConfig({ ...draft, maxPollConcurrency: 51 }, true)).toContain('1–50')
  })

  it('validates API and optional callback URLs', () => {
    const draft = createKlingConfigDraft({ ...config, apiKeyConfigured: true })

    expect(validateKlingConfig({ ...draft, baseUrl: '' }, true)).toContain('Base URL')
    expect(validateKlingConfig({ ...draft, baseUrl: 'http://api.example.com' }, true)).toContain('Base URL')
    expect(validateKlingConfig({ ...draft, callbackUrl: 'https://example.com/kling/callback' }, true)).toBe('')
    expect(validateKlingConfig({ ...draft, callbackUrl: 'not-a-url' }, true)).toContain('回调 URL')
  })

  it('normalizes API and callback URLs in the patch', () => {
    const draft = createKlingConfigDraft({ ...config, apiKeyConfigured: true })

    expect(buildKlingConfigPatch({
      ...draft,
      baseUrl: ' https://api-singapore.klingai.com/ ',
      callbackUrl: ' https://example.com/kling/callback ',
    })).toMatchObject({
      baseUrl: 'https://api-singapore.klingai.com',
      callbackUrl: 'https://example.com/kling/callback',
    })
    expect(buildKlingConfigPatch({ ...draft, callbackUrl: ' ' })).toMatchObject({
      clearCallbackUrl: true,
    })
    expect(buildKlingConfigPatch({ ...draft, callbackUrl: ' ' })).not.toHaveProperty('callbackUrl')
  })

  it('presents official API lifecycle states without CLI guidance', () => {
    expect(klingApiStatusPresentation('KLING_API_READY', true)).toMatchObject({
      label: '已就绪',
      tone: 'success',
    })
    expect(klingApiStatusPresentation('KLING_API_CONFIGURED_UNVERIFIED', true).message).toContain('只读')
    expect(klingApiStatusPresentation('KLING_API_AUTHENTICATION_FAILED', true).message).toContain('API Key')
    expect(klingApiStatusPresentation('KLING_API_VERIFICATION_FAILED', true).message).toContain('区域')
    expect(klingApiStatusPresentation('KLING_API_KEY_MISSING', false).label).toBe('缺少密钥')
    expect(klingApiStatusPresentation('KLING_API_DISABLED', false).message).toContain('官方 API')
  })

  it('formats the compatibility version field as an API version', () => {
    expect(formatKlingApiVersion('api-2.0')).toBe('API 2.0')
    expect(formatKlingApiVersion(null)).toBe('')
  })
})
