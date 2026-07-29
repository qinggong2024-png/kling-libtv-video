import { describe, expect, it } from 'vitest'
import { formatRiskFlags } from './riskLabels'

describe('formatRiskFlags', () => {
  it('renders garment conflicts as Chinese guidance', () => {
    expect(formatRiskFlags(['STORYBOARD_GARMENT_CONFLICT'])).toBe(
      '模特场景图与产品图中的服装不一致，款式、颜色、图案或细节可能偏差',
    )
  })

  it('preserves unrecognized values for troubleshooting', () => {
    expect(formatRiskFlags(['LOW_DETAIL_REFERENCE', 'UNKNOWN_FLAG'])).toBe(
      '参考图细节不足，面料、印花或标识可能无法准确还原、UNKNOWN_FLAG',
    )
  })
})
