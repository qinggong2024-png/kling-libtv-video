import { describe, expect, it } from 'vitest'

import { FEEDBACK_OPTIONS, toggleFeedbackReason } from './feedbackOptions'

describe('generation feedback details', () => {
  it('keeps like and dislike reasons in separate option sets', () => {
    expect(FEEDBACK_OPTIONS.LIKE.map((option) => option.value)).toContain('GARMENT_ACCURATE')
    expect(FEEDBACK_OPTIONS.DISLIKE.map((option) => option.value)).toContain('GARMENT_DISTORTED')
    expect(FEEDBACK_OPTIONS.LIKE.map((option) => option.value)).not.toContain('GARMENT_DISTORTED')
  })

  it('adds, removes, and limits detailed reasons', () => {
    const first = toggleFeedbackReason([], 'GARMENT_ACCURATE')
    const second = toggleFeedbackReason(first, 'PRODUCT_CLEAR')
    const third = toggleFeedbackReason(second, 'NATURAL_MOTION')

    expect(toggleFeedbackReason(third, 'GOOD_PACING')).toEqual(third)
    expect(toggleFeedbackReason(third, 'PRODUCT_CLEAR')).toEqual([
      'GARMENT_ACCURATE',
      'NATURAL_MOTION',
    ])
  })
})
