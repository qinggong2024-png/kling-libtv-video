import { describe, expect, it } from 'vitest'
import { productSurfaceView, readProductSurface } from './productNavigation'

describe('Creative OS product navigation', () => {
  it('maps product surfaces onto the existing operational views', () => {
    expect(productSurfaceView('workspace')).toBe('make')
    expect(productSurfaceView('director')).toBe('images')
    expect(productSurfaceView('image')).toBe('images')
    expect(productSurfaceView('video')).toBe('make')
    expect(productSurfaceView('review')).toBe('records')
    expect(productSurfaceView('assets')).toBe('library')
    expect(productSurfaceView('memory')).toBe('make')
  })

  it('recognizes only matching pane and view combinations', () => {
    expect(readProductSurface('?view=make&pane=workspace')).toBe('workspace')
    expect(readProductSurface('?view=images&pane=director')).toBe('director')
    expect(readProductSurface('?view=images&pane=image')).toBe('image')
    expect(readProductSurface('?view=records&pane=review')).toBe('review')
    expect(readProductSurface('?view=library&pane=assets')).toBe('assets')
    expect(readProductSurface('?view=make&pane=memory')).toBe('memory')
    expect(readProductSurface('?view=make&pane=director')).toBeNull()
  })

  it('preserves legacy and task links outside the product surface layer', () => {
    expect(readProductSurface('?view=images')).toBeNull()
    expect(readProductSurface('?view=make')).toBeNull()
    expect(readProductSurface('?view=records')).toBeNull()
    expect(readProductSurface('?task=task-1')).toBeNull()
    expect(readProductSurface('?view=make&pane=workspace&task=task-1')).toBeNull()
  })
})
