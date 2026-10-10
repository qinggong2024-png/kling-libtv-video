import { describe, expect, it } from 'vitest'
import { createDirectorDraft, isDirectorIntakeReady, selectDirectorDirection } from './directorModel'

describe('Director Studio planning model', () => {
  it('starts with an explicit intake boundary and three candidate directions', () => {
    const draft = createDirectorDraft()
    expect(draft.phase).toBe('intake')
    expect(draft.directions.map((direction) => direction.id)).toEqual(['A', 'B', 'C'])
    expect(isDirectorIntakeReady(draft.intake)).toBe(false)
  })

  it('selects a direction without creating a generation task', () => {
    const draft = createDirectorDraft()
    const next = selectDirectorDirection(draft, 'B')
    expect(next.phase).toBe('package')
    expect(next.selectedDirectionId).toBe('B')
    expect('taskId' in next).toBe(false)
  })

  it('requires a product front before planning can begin', () => {
    const draft = createDirectorDraft()
    expect(isDirectorIntakeReady({ ...draft.intake, productFrontName: 'front.jpg' })).toBe(true)
  })
})
