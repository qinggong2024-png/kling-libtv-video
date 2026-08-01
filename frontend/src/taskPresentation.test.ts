import { describe, expect, it } from 'vitest'

import {
  isAnalysisFailure,
  statusPresentation,
  taskFailureMessage,
  taskStatus,
  validateCompatibleBaseUrl,
  variantDisplayName,
  variantLabelClass,
  variantShortLabel,
} from './taskPresentation'
import type { Variant } from './types'

describe('task presentation', () => {
  it('keeps provider and analysis failures distinguishable', () => {
    const task = { phase: 'ACTION_REQUIRED', phaseReasonCode: 'ANALYSIS_TIMEOUT' }
    expect(isAnalysisFailure(task)).toBe(true)
    expect(taskStatus(task)).toEqual({ label: '方案分析超时', tone: 'danger' })
    expect(taskFailureMessage(task)).toContain('等待上限')
    expect(statusPresentation('ACTION_REQUIRED')).toEqual({ label: '任务需要处理', tone: 'danger' })
  })

  it('validates compatible model gateway URLs', () => {
    expect(validateCompatibleBaseUrl('https://gateway.example.com/v1')).toBe('')
    expect(validateCompatibleBaseUrl('http://localhost:8080/v1')).toBe('')
    expect(validateCompatibleBaseUrl('http://gateway.example.com/v1')).toContain('HTTPS')
    expect(validateCompatibleBaseUrl('https://user:secret@gateway.example.com/v1')).toContain('账号密码')
  })

  it('presents generated results by index and legacy variants by kind', () => {
    const result = { kind: 'DYNAMIC', variantIndex: 2 } as Variant
    const stable = { kind: 'STABLE', variantIndex: null } as Variant
    expect(variantShortLabel(result)).toBe('2')
    expect(variantDisplayName(result)).toBe('结果 2')
    expect(variantLabelClass(result)).toBe('variant-label--result')
    expect(variantShortLabel(stable)).toBe('稳')
  })
})
