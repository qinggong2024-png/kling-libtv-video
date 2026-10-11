import { describe, expect, it } from 'vitest'
import { createDirectorDraft } from './directorModel'
import { selectDirectorHandoff, selectDirectorPlanningSnapshot } from './directorSelectors'

describe('Director Studio planning selectors', () => {
  it('keeps planning state separate from execution state before a package exists', () => {
    const draft = createDirectorDraft()
    draft.intake.productFrontFile = new File(['front'], 'front.png', { type: 'image/png' })
    draft.selectedDirectionId = 'A'
    const snapshot = selectDirectorPlanningSnapshot(null, draft, 'project-1')

    expect(snapshot.brief.productName).toBe('')
    expect(snapshot.selectedDirectionId).toBe('A')
    expect(snapshot.productionPackage).toBeNull()
    expect(snapshot.handoff).toBeNull()
  })

  it('creates a read-only handoff context from an existing production package', () => {
    const draft = createDirectorDraft()
    draft.intake.productFrontFile = new File(['front'], 'front.png', { type: 'image/png' })
    draft.selectedDirectionId = 'B'
    const workflow = {
      id: 'task-1',
      status: 'IMAGE_REVIEW',
      state_version: 2,
      mode: 'OFFLINE_FAKE_ONLY',
      snapshot: {
        asset: { sha256: 'sha', width: 1, height: 1, object_key: 'asset' },
        trace: [],
        candidates: [],
        calls: 0,
        cost_micros: 0,
        total_calls: 0,
        total_cost_micros: 0,
        package: {
          package_id: 'package-1',
          revision: 3,
          parent_package_id: null,
          locks_hash: 'locks',
          facts_revision: 1,
          preservation_hash: 'preservation',
          ruleset: 'rules',
          shot_id: 'FIRST_FRAME' as const,
          prompt: 'prompt',
          reality: [],
        },
      },
    }

    const handoff = selectDirectorHandoff(workflow, draft, 'project-1')
    expect(handoff).toMatchObject({
      source: 'director-studio',
      projectId: 'project-1',
      directionId: 'B',
      packageId: 'package-1',
      packageRevision: 3,
      references: {
        productFront: true,
        selectedDirection: true,
        productionPackage: true,
      },
    })
  })
})
