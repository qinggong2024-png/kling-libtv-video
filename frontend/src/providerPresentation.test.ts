import { describe, expect, it } from 'vitest'

import {
  generationProviderKind,
  providerActionRequiredMessage,
  providerProgress,
  providerTimingStageLabel,
  variantExecutionMessage,
} from './providerPresentation'

describe('provider presentation', () => {
  it('normalizes the configured Kling provider without treating it as LibTV', () => {
    expect(generationProviderKind('kling')).toBe('kling')
    expect(generationProviderKind('kling_official_cli')).toBe('kling')
    expect(generationProviderKind('kling_official_api')).toBe('kling')
    expect(generationProviderKind('bach')).toBe('bach')
    expect(generationProviderKind('libtv')).toBe('legacy')
  })

  it('uses provider-specific queue and generation copy', () => {
    expect(providerProgress('QUEUED', 'kling').label).toContain('可灵官方 API')
    expect(providerProgress('QUEUED', 'kling_official_api').label).toContain('可灵官方 API')
    expect(providerProgress('QUEUED', 'libtv').label).toContain('历史生成通道')
    expect(providerProgress('QUEUED', 'bach').label).toContain('Bach Image-to-Video API')
    expect(providerTimingStageLabel('MATERIALIZATION', 'kling')).toBe(
      '可灵官方 API 素材准备',
    )
    expect(providerTimingStageLabel('MATERIALIZATION', 'libtv')).toBe('历史任务素材准备')
  })

  it('shows distinct uncertain-state recovery boundaries', () => {
    const base = {
      generationStatus: 'UNKNOWN',
      downloadStatus: 'PENDING',
      downloadArtifactId: null,
      errorCode: null,
    }
    expect(variantExecutionMessage({ ...base, provider: 'kling_official_cli' })).toContain('任务 ID')
    expect(variantExecutionMessage({ ...base, provider: 'kling_official_api' })).toContain(
      '可灵官方 API',
    )
    expect(variantExecutionMessage({ ...base, provider: 'libtv' })).toContain('历史任务')
  })

  it('shows actionable provider failure details', () => {
    expect(variantExecutionMessage({
      generationStatus: 'FAILED',
      downloadStatus: 'FAILED',
      downloadArtifactId: null,
      errorCode: 'KLING_API_RATE_LIMITED',
      providerErrorMessage: 'Too many requests',
      providerErrorRetryable: true,
      provider: 'kling_official_api',
    })).toBe('可灵官方 API：KLING_API_RATE_LIMITED · Too many requests · 可以重试')
  })

  it('explains that unsupported Bach product references were never submitted', () => {
    const message = providerActionRequiredMessage('BACH_ELEMENTS_NOT_IN_P1', 'bach')
    expect(message).toContain('不能使用单独的产品参考图')
    expect(message).toContain('没有调用任何生成 API')
    expect(variantExecutionMessage({
      generationStatus: 'PENDING',
      downloadStatus: 'PENDING',
      downloadArtifactId: null,
      errorCode: null,
      provider: 'bach',
      providerTaskId: null,
    }, 'bach', 'ACTION_REQUIRED')).toBe(
      'Bach Image-to-Video API：预检未通过，未提交生成',
    )
  })
})
