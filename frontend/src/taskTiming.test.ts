import { describe, expect, it } from 'vitest'

import {
  formatDurationSeconds,
  formatElapsed,
  parseTaskTimestamp,
  currentProductionStageIndex,
  visibleProductionStageKeys,
  visibleTaskTimingStageKeys,
} from './taskTiming'

describe('task timing', () => {
  it('treats timezone-less API timestamps as UTC', () => {
    expect(parseTaskTimestamp('2026-07-28T06:00:00')).toBe(
      Date.UTC(2026, 6, 28, 6, 0, 0),
    )
  })

  it('calculates elapsed time from explicit start and end instants', () => {
    expect(
      formatElapsed('2026-07-28T06:00:00', '2026-07-28T07:25:30+00:00'),
    ).toBe('1 小时 25 分钟')
  })

  it('does not show a misleading negative duration for clock skew', () => {
    expect(
      formatElapsed('2026-07-28T07:00:00Z', '2026-07-28T06:59:30Z'),
    ).toBe('0 秒')
  })

  it('formats live stage durations with seconds', () => {
    expect(formatDurationSeconds(38 * 60 + 7)).toBe('38 分 7 秒')
    expect(formatDurationSeconds(2 * 3600 + 3 * 60)).toBe('2 小时 3 分')
  })

  it('only shows real execution stages for fixed-template tasks', () => {
    expect(visibleTaskTimingStageKeys('FIXED_TEMPLATE')).toEqual([
      'SOURCE_UPLOAD',
      'GENERATION',
      'DOWNLOAD',
    ])
  })

  it('keeps analysis and confirmation stages for legacy tasks', () => {
    expect(visibleTaskTimingStageKeys('LEGACY_ANALYSIS')).toEqual([
      'SOURCE_UPLOAD',
      'ANALYSIS',
      'CONFIRMATION',
      'MATERIALIZATION',
      'GENERATION',
      'DOWNLOAD',
    ])
  })

  it('shows custom prompt tasks as a direct generation flow', () => {
    expect(visibleProductionStageKeys('FIXED_TEMPLATE', 'custom')).toEqual([
      'MATERIALS',
      'GENERATION',
      'RESULT',
    ])
    expect(currentProductionStageIndex('PREPARING', 'FIXED_TEMPLATE', 'custom')).toBe(1)
    expect(currentProductionStageIndex('QUEUED', 'FIXED_TEMPLATE', 'custom')).toBe(1)
    expect(currentProductionStageIndex('DELIVERABLE', 'FIXED_TEMPLATE', 'custom')).toBe(2)
  })

  it('keeps template and preflight visible for automatic fixed-template tasks', () => {
    expect(visibleProductionStageKeys('FIXED_TEMPLATE', 'automatic')).toEqual([
      'MATERIALS',
      'TEMPLATE',
      'PREFLIGHT',
      'GENERATION',
      'RESULT',
    ])
  })
})
