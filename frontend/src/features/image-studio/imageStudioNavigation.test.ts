import { describe, expect, it } from 'vitest'
import { readImageStudioView } from './imageStudioNavigation'

describe('Image Studio information architecture navigation', () => {
  it('opens image creation directly when no task mode is selected', () => {
    expect(readImageStudioView('?view=images&pane=image')).toBe('image-to-image')
    expect(readImageStudioView('?view=images')).toBe('image-to-image')
  })

  it('keeps the high frequency workflows as first-level destinations', () => {
    expect(readImageStudioView('?view=images&pane=image&imageMode=image-to-image')).toBe('image-to-image')
    expect(readImageStudioView('?view=images&pane=image&imageMode=text-to-image')).toBe('text-to-image')
    expect(readImageStudioView('?view=images&pane=image&imageMode=batch')).toBe('batch-create')
    expect(readImageStudioView('?view=images&pane=image&imageMode=records')).toBe('records')
  })

  it('falls back to direct creation for unknown and former home modes', () => {
    expect(readImageStudioView('?view=images&pane=image&imageMode=assets')).toBe('image-to-image')
    expect(readImageStudioView('?view=images&pane=image&imageMode=home')).toBe('image-to-image')
  })

  it('preserves the professional destinations beneath batch production', () => {
    for (const mode of ['batch-create', 'batch-products', 'batch-storyboard']) {
      expect(readImageStudioView(`?view=images&pane=image&imageMode=${mode}`)).toBe(mode)
    }
  })
})
