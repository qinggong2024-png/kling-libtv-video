import { describe, expect, it } from 'vitest'
import { mergeAssetReferences, toAssetReference } from './adapters/assets'
import { mergeProjectMetadata } from './adapters/metadata'
import { readProjectIdFromSearch, toCreativeWorkflowContext } from './adapters/navigation'
import { createCreativeProject } from './project'
import {
  selectCreativeIntelligenceSnapshot,
  selectProjectAsset,
  selectProjectStage,
  selectProjectTaskId,
} from './selectors'

describe('CreativeProject adapters and selectors', () => {
  it('adapts navigation without changing existing view semantics', () => {
    expect(readProjectIdFromSearch('?view=records&project=project-1')).toBe('project-1')
    expect(toCreativeWorkflowContext({
      search: '?view=make&task=task-1',
      view: 'make',
      detailId: 'task-1',
    })).toEqual({ activeView: 'make', activeTaskId: 'task-1' })
  })

  it('merges asset references by stable identity', () => {
    const current = [toAssetReference({ id: 'asset-1', kind: 'product', source: 'upload' })]
    const incoming = [
      toAssetReference({ id: 'asset-1', kind: 'product', source: 'library', revision: 2 }),
      toAssetReference({ id: 'asset-2', kind: 'scene', source: 'library' }),
    ]

    expect(mergeAssetReferences(current, incoming)).toEqual(incoming)
  })

  it('keeps project metadata and revision separate from execution state', () => {
    const project = createCreativeProject({
      id: 'project-1',
      assets: [{ id: 'asset-1', kind: 'product', source: 'upload' }],
      workflowContext: { currentStage: 'direction' },
      intelligenceSnapshot: { realityReference: { realityDNAId: 'reality-1' }, referenceStrength: 0.8 },
      revision: 3,
    })
    const updated = mergeProjectMetadata(project, { campaign: 'spring' })

    expect(updated.revision).toBe(4)
    expect(selectProjectStage(updated)).toBe('direction')
    expect(selectProjectTaskId(updated)).toBeNull()
    expect(selectProjectAsset(updated, 'asset-1')?.kind).toBe('product')
    expect(selectCreativeIntelligenceSnapshot(updated)?.realityReference?.realityDNAId).toBe('reality-1')
    expect('phase' in updated).toBe(false)
  })
})
