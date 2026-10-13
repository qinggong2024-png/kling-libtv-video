import { describe, expect, it } from 'vitest'
import { readImageStudioView } from './imageStudioNavigation'

describe('Image Studio information architecture navigation', () => {
  it('opens the studio home when no task mode is selected', () => {
    expect(readImageStudioView('?view=images&pane=image')).toBe('home')
    expect(readImageStudioView('?view=images')).toBe('home')
  })

  it('keeps the high frequency workflows as first-level destinations', () => {
    expect(readImageStudioView('?view=images&pane=image&imageMode=image-to-image')).toBe('image-to-image')
    expect(readImageStudioView('?view=images&pane=image&imageMode=text-to-image')).toBe('text-to-image')
    expect(readImageStudioView('?view=images&pane=image&imageMode=batch')).toBe('batch')
    expect(readImageStudioView('?view=images&pane=image&imageMode=records')).toBe('records')
  })

  it('falls back to the home entry point for unknown modes', () => {
    expect(readImageStudioView('?view=images&pane=image&imageMode=assets')).toBe('home')
  })
})
