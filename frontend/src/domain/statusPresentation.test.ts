import { describe, expect, it } from 'vitest'

import {
  attemptStatusPresentation,
  imageStatusPresentation,
  statusPresentation,
  taskStatusPresentation,
} from './statusPresentation'

const task = (phase: string, overrides: Partial<{
  phaseReasonCode: string | null
  canConfirm: boolean
  canRetryAnalysis: boolean
  canDownload: boolean
}> = {}) => ({
  phase,
  phaseReasonCode: overrides.phaseReasonCode ?? null,
  actionCapabilities: {
    canConfirm: overrides.canConfirm ?? false,
    canRetryAnalysis: overrides.canRetryAnalysis ?? false,
    canDownload: overrides.canDownload ?? false,
  },
}) as never

describe('status presentation', () => {
  it.each([
    ['GENERATING', 'processing', 'active', '正在生成视频'],
    ['DELIVERABLE', 'completed', 'success', '已完成'],
    ['PARTIALLY_DELIVERABLE', 'partial', 'warning', '部分完成'],
    ['ACTION_REQUIRED', 'manual', 'danger', '任务需要处理'],
    ['AWAITING_CONFIRMATION', 'confirmation', 'warning', '等待确认方案'],
  ] as const)('maps video task %s to %s semantics', (phase, semantic, tone, label) => {
    expect(taskStatusPresentation(task(phase))).toMatchObject({ semantic, tone, label })
  })

  it('maps analysis failures to a retry-aware failed presentation', () => {
    expect(taskStatusPresentation(task('ACTION_REQUIRED', {
      phaseReasonCode: 'ANALYSIS_TIMEOUT',
      canRetryAnalysis: true,
    }))).toMatchObject({
      semantic: 'failed',
      tone: 'danger',
      label: '方案分析超时',
      primaryAction: 'RETRY',
      actionLabel: '重试任务',
    })
  })

  it('uses the same semantics for video attempt statuses', () => {
    expect(statusPresentation({ source: 'attempt', value: 'SUCCEEDED' })).toMatchObject({
      semantic: 'completed',
      tone: 'success',
      primaryAction: 'DOWNLOAD',
    })
    expect(statusPresentation({ source: 'attempt', value: 'FAILED', retryable: false })).toMatchObject({
      semantic: 'failed',
      tone: 'danger',
      primaryAction: 'REVIEW',
      actionLabel: '人工处理',
    })
    expect(attemptStatusPresentation({
      generationStatus: 'UNKNOWN',
      retryable: null,
      providerErrorRetryable: null,
      downloadArtifactId: null,
    })).toMatchObject({
      semantic: 'unknown',
      tone: 'warning',
      primaryAction: 'RECONCILE',
    })
  })

  it('maps image task statuses without changing their business values', () => {
    expect(imageStatusPresentation('running')).toMatchObject({
      semantic: 'processing',
      tone: 'active',
      label: '正在生成图片',
    })
    expect(imageStatusPresentation('completed')).toMatchObject({
      semantic: 'completed',
      tone: 'success',
    })
    expect(imageStatusPresentation('write_uncertain')).toMatchObject({
      semantic: 'unknown',
      tone: 'warning',
      label: '提交待确认',
      primaryAction: 'RECONCILE',
    })
  })

  it('keeps unknown and empty statuses safe and actionable', () => {
    for (const value of [null, '', 'A_STATUS_ADDED_LATER']) {
      expect(statusPresentation({ source: 'attempt', value })).toMatchObject({
        semantic: 'unknown',
        label: '状态待确认',
        tone: 'warning',
        primaryAction: 'RECONCILE',
      })
    }
  })

  it('does not promise an unavailable action', () => {
    expect(statusPresentation({
      source: 'task',
      value: 'DELIVERABLE',
      canDownload: false,
    })).toMatchObject({
      semantic: 'completed',
      actions: ['NONE'],
      primaryAction: null,
      actionLabel: null,
    })
  })
})
