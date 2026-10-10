import { describe, expect, it } from 'vitest'
import { createCreativeProject } from './project'

describe('CreativeProject foundation', () => {
  it('creates a project container without introducing task execution state', () => {
    const project = createCreativeProject({
      id: 'project-1',
      name: 'Test project',
      assets: [{ id: 'asset-1', kind: 'product', source: 'upload' }],
    })

    expect(project.id).toBe('project-1')
    expect(project.assets).toHaveLength(1)
    expect(project.metadata).toBeUndefined()
    expect('phase' in project).toBe(false)
  })
})
