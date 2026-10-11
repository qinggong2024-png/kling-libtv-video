import { describe, expect, it } from 'vitest'
import { createCreativeProject } from '../../creative-project/project'
import { readDirectorPlanningSnapshot, selectDirectorHandoffFromProject } from './directorHandoff'

describe('Director Studio handoff preparation', () => {
  it('reads a valid handoff from project metadata without creating execution state', () => {
    const project = createCreativeProject({
      id: 'project-1',
      metadata: {
        directorPlanning: {
          brief: {
            productName: 'Jacket',
            brandMode: 'generic',
            brandName: '',
            objective: 'Show fabric texture',
            audience: 'Adults',
            notes: '',
          },
          candidates: [],
          selectedDirectionId: 'A',
          productionPackage: null,
          handoff: {
            source: 'director-studio',
            projectId: 'project-1',
            directionId: 'A',
            packageId: 'package-1',
            packageRevision: 2,
            shotId: 'FIRST_FRAME',
            references: {
              productFront: true,
              selectedDirection: true,
              productionPackage: true,
            },
          },
        },
      },
    })

    expect(selectDirectorHandoffFromProject(project)?.packageId).toBe('package-1')
    expect(readDirectorPlanningSnapshot(project)?.selectedDirectionId).toBe('A')
    expect('phase' in project).toBe(false)
  })

  it('rejects incomplete or malformed handoff metadata', () => {
    const project = createCreativeProject({
      id: 'project-1',
      metadata: {
        directorPlanning: {
          handoff: {
            source: 'director-studio',
            packageId: 'package-1',
            shotId: 'FIRST_FRAME',
          },
        },
      },
    })

    expect(selectDirectorHandoffFromProject(project)).toBeNull()
  })
})
