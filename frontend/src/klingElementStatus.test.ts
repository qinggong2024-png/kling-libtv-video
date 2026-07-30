import { describe, expect, it } from 'vitest'

import {
  getKlingElementStatusGroup,
  getKlingElementStatusLabel,
  isKlingElementAvailable,
  normalizeKlingElementStatus,
} from './klingElementStatus'

describe('Kling element status helpers', () => {
  it.each(['active', 'completed', 'ready', 'succeed', 'succeeded', 'success'])(
    'treats %s as available',
    (status) => {
      expect(isKlingElementAvailable(status)).toBe(true)
      expect(getKlingElementStatusGroup(status)).toBe('available')
      expect(getKlingElementStatusLabel(status)).toBe('可用')
    },
  )

  it('normalizes whitespace and casing before matching', () => {
    expect(normalizeKlingElementStatus('  SuCcEeD ')).toBe('succeed')
    expect(isKlingElementAvailable('  SuCcEeD ')).toBe(true)
  })

  it.each(['failed', 'error', 'cancelled', 'canceled'])(
    'treats %s as failed',
    (status) => {
      expect(getKlingElementStatusGroup(status)).toBe('failed')
      expect(getKlingElementStatusLabel(status)).toBe('失败')
    },
  )

  it('keeps submitted and unknown statuses unavailable', () => {
    expect(getKlingElementStatusLabel('submitted')).toBe('创建中')
    expect(getKlingElementStatusGroup('processing')).toBe('processing')
    expect(isKlingElementAvailable('unknown')).toBe(false)
  })
})
