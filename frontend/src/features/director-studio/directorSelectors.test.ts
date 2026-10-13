import { afterEach, describe, expect, it, vi } from 'vitest'
import { createDirectorDraft } from './directorModel'
import { selectDirectorHandoff, selectDirectorPlanningSnapshot } from './directorSelectors'
import { createCreativeProject } from '../../creative-project/project'
import { persistCreativeProject, readPersistedCreativeProject } from '../../creative-project/recovery'
import { prepareDirectorFixedOffline } from './productionBridge'

function fakeStore(): Storage {
  const data = new Map<string, string>()
  return {
    get length() { return data.size },
    clear: () => data.clear(),
    getItem: (key) => data.get(key) ?? null,
    key: (index) => [...data.keys()][index] ?? null,
    removeItem: (key) => { data.delete(key) },
    setItem: (key, value) => { data.set(key, value) },
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

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

  it('persists storyboard handoff metadata that remains usable after reload', () => {
    const store = fakeStore()
    vi.stubGlobal('localStorage', store)
    const draft = createDirectorDraft()
    draft.intake.productFrontFile = new File(['front'], 'front.png', { type: 'image/png' })
    draft.selectedDirectionId = 'A'
    const sourceImageHash = 'a'.repeat(64)
    const workflow = {
      id: 'task-1',
      status: 'STORYBOARD_REVIEW',
      state_version: 9,
      mode: 'OFFLINE_FAKE_ONLY' as const,
      snapshot: {
        asset: { sha256: sourceImageHash, width: 1, height: 1, object_key: 'asset' },
        trace: [],
        candidates: [],
        calls: 0,
        cost_micros: 0,
        total_calls: 0,
        total_cost_micros: 0,
        package: {
          package_id: 'first-frame-package-1',
          revision: 3,
          parent_package_id: null,
          locks_hash: 'locks',
          facts_revision: 1,
          preservation_hash: 'preservation',
          ruleset: 'rules',
          shot_id: 'FIRST_FRAME' as const,
          prompt: 'first frame',
          reality: [],
        },
        plan: {
          directions: [{ id: 'A' as const, scene: 'studio', behavior: 'stand' }],
          selected_direction: 'A' as const,
        },
        storyboard: {
          packages: {
            SHOT_01: {
              package_id: 'storyboard-package-1',
              revision: 4,
              parent_package_id: 'first-frame-package-1',
              locks_hash: 'storyboard-locks',
              facts_revision: 1,
              preservation_hash: 'storyboard-preservation',
              ruleset: 'rules',
              purpose: 'VIDEO_STORYBOARD' as const,
              shot_id: 'SHOT_01',
              prompt: 'storyboard',
              reality: [],
            },
          },
          candidates: [{
            candidate_id: 'storyboard-candidate-1',
            package_id: 'storyboard-package-1',
            authorization_id: 'authorization-1',
            shot_id: 'SHOT_01',
            batch_id: 'storyboard-candidate-1-batch',
            item_id: 'storyboard-candidate-1-item',
            output_id: 'storyboard-candidate-1-output',
            synthetic: true,
            qualified: true,
            revision_index: 1,
            sha256: 'b'.repeat(64),
            object_key: 'offline/storyboard-candidate-1.png',
            media_evidence: 'synthetic',
          }],
          selections: {
            SHOT_01: {
              candidate_id: 'storyboard-candidate-1',
              package_id: 'storyboard-package-1',
              shot_id: 'SHOT_01',
              batch_id: 'storyboard-candidate-1-batch',
              item_id: 'storyboard-candidate-1-item',
              output_id: 'storyboard-candidate-1-output',
              synthetic: true,
            },
          },
          latest_reviews: {},
          shot_mappings: {
            SHOT_01: {
              shot_id: 'SHOT_01',
              package_id: 'storyboard-package-1',
              candidate_id: 'storyboard-candidate-1',
              source_image_hash: sourceImageHash,
              batch_id: 'storyboard-candidate-1-batch',
              item_id: 'storyboard-candidate-1-item',
              output_id: 'storyboard-candidate-1-output',
              object_key: 'offline/storyboard-candidate-1.png',
            },
          },
        },
      },
    }

    const planning = selectDirectorPlanningSnapshot(workflow, draft, 'project-1')
    const project = createCreativeProject({
      id: 'project-1',
      workflowContext: { creativeTaskId: 'task-1' },
      metadata: { directorPlanning: planning },
    })

    expect(persistCreativeProject(project)).toBe(true)
    const restored = readPersistedCreativeProject(createCreativeProject({ id: 'project-1' }))
    const preparation = prepareDirectorFixedOffline(restored)

    expect(preparation).toMatchObject({
      status: 'READY',
      creativeTaskId: 'task-1',
      packageId: 'storyboard-package-1',
      packageRevision: 4,
      shotId: 'SHOT_01',
      candidateId: 'storyboard-candidate-1',
      sourceImageHash,
      shotMapping: {
        outputId: 'storyboard-candidate-1-output',
      },
      input: {
        executionMode: 'director_fixed',
        providerSubmissionAllowed: false,
        deliverableEligible: false,
      },
    })
  })
})
