import { describe, expect, it } from 'vitest'
import { ProductionComposer } from '../production/ProductionComposer'
import { VideoStudio } from './index'

describe('VideoStudio compatibility boundary', () => {
  it('uses the existing composer without adding a wrapper or execution owner', () => {
    expect(VideoStudio).toBe(ProductionComposer)
  })
})
