import { describe, expect, it } from 'vitest'

import {
  generationProviderKind,
  providerProgress,
  providerTimingStageLabel,
  variantExecutionMessage,
} from './providerPresentation'

describe('provider presentation', () => {
  it('normalizes the configured Kling provider without treating it as LibTV', () => {
    expect(generationProviderKind('kling')).toBe('kling')
    expect(generationProviderKind('kling_official_cli')).toBe('kling')
    expect(generationProviderKind('kling_official_api')).toBe('kling')
    expect(generationProviderKind('libtv')).toBe('libtv')
  })

  it('uses provider-specific queue and generation copy', () => {
    expect(providerProgress('QUEUED', 'kling').label).toContain('可灵官方 Provider')
    expect(providerProgress('QUEUED', 'kling_official_api').label).toContain('Kling API')
    expect(providerProgress('QUEUED', 'libtv').label).toContain('LibTV CLI')
    expect(providerTimingStageLabel('MATERIALIZATION', 'kling')).toBe(
      '可灵官方 Provider 素材准备',
    )
    expect(providerTimingStageLabel('MATERIALIZATION', 'libtv')).toBe('LibTV CLI 画布准备')
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
      'Kling API',
    )
    expect(variantExecutionMessage({ ...base, provider: 'libtv' })).toContain('--run')
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
    })).toBe('Kling API：KLING_API_RATE_LIMITED · Too many requests · 可以重试')
  })
})
