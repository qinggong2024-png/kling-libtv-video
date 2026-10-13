import { afterEach, describe, expect, it, vi } from 'vitest'
import { createCreativeProject } from '../../creative-project/project'
import {
  clearPersistedCreativeProject,
  persistCreativeProject,
  readPersistedCreativeProject,
} from '../../creative-project/recovery'
import type { DirectorTaskResponse } from './directorApi'
import {
  classifyDirectorRecoveryError,
  createDirectorTaskRecovery,
  draftFromPersistedDirectorProject,
  validateDirectorProductReference,
  validateDirectorTaskRecovery,
} from './directorRecovery'

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

function task(overrides: Partial<DirectorTaskResponse> = {}): DirectorTaskResponse {
  return {
    id: 'task-1',
    status: 'IMAGE_REVIEW',
    state_version: 4,
    mode: 'OFFLINE_FAKE_ONLY',
    snapshot: {
      asset: {
        sha256: 'a'.repeat(64),
        width: 100,
        height: 100,
        object_key: 'creative/front',
      },
      product_version: {
        product_id: 'product-1',
        product_version_id: 'version-1',
        facts_revision: 1,
      },
      trace: [],
      candidates: [],
      calls: 1,
      cost_micros: 1,
      total_calls: 1,
      total_cost_micros: 1,
    },
    ...overrides,
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Director task recovery', () => {
  it('persists only JSON-safe project references and never the browser File', () => {
    vi.stubGlobal('localStorage', fakeStore())
    const project = createCreativeProject({
      id: 'project-1',
      workflowContext: { creativeTaskId: 'task-1' },
      metadata: {
        directorRecovery: {
          schemaVersion: 1,
          creative_task_id: 'task-1',
          product_reference: { product_id: 'product-1' },
          planning_snapshot_index: { state_version: 4, saved_at: '2026-10-12T00:00:00.000Z' },
        },
        transientFile: new File(['front'], 'front.png'),
      },
    })

    expect(persistCreativeProject(project)).toBe(true)
    const restored = readPersistedCreativeProject(createCreativeProject({ id: 'project-1' }))
    expect(restored.workflowContext?.creativeTaskId).toBe('task-1')
    expect(restored.metadata?.directorRecovery).toMatchObject({ creative_task_id: 'task-1' })
    expect(restored.metadata?.transientFile).toBeUndefined()

    clearPersistedCreativeProject('project-1')
    expect(readPersistedCreativeProject(createCreativeProject({ id: 'project-1' })).metadata).toBeUndefined()
  })

  it('creates and validates a recovery reference against the server task snapshot', () => {
    const reference = createDirectorTaskRecovery(task(), 'product-fallback', new Date('2026-10-12T00:00:00.000Z'))
    expect(reference).toEqual({
      schemaVersion: 1,
      creative_task_id: 'task-1',
      product_reference: {
        product_id: 'product-1',
        product_version_id: 'version-1',
        source_sha256: 'a'.repeat(64),
      },
      planning_snapshot_index: {
        state_version: 4,
        saved_at: '2026-10-12T00:00:00.000Z',
      },
    })
    expect(validateDirectorTaskRecovery(reference, task())).toEqual({ valid: true })
    expect(validateDirectorTaskRecovery(reference, task({
      snapshot: {
        ...task().snapshot,
        asset: { ...task().snapshot.asset, sha256: 'b'.repeat(64) },
      },
    }))).toEqual({ valid: false, reason: 'PRODUCT_REFERENCE_EXPIRED' })
  })

  it('blocks a stale product version and classifies recoverable GET failures', () => {
    const reference = createDirectorTaskRecovery(task())
    expect(validateDirectorProductReference(reference, {
      id: 'product-1',
      current_version_id: 'version-2',
    })).toEqual({ valid: false, reason: 'PRODUCT_VERSION_STALE' })
    expect(classifyDirectorRecoveryError({ status: 404, code: 'TASK_NOT_FOUND' })).toBe('TASK_NOT_FOUND')
    expect(classifyDirectorRecoveryError({ code: 'ASSET_MISSING' })).toBe('PRODUCT_REFERENCE_EXPIRED')
    expect(classifyDirectorRecoveryError(new Error('offline'))).toBe('NETWORK_ERROR')
  })

  it('restores a local direction choice to Creative Direction until a package exists', () => {
    const project = createCreativeProject({
      id: 'project-1',
      metadata: {
        directorPlanning: {
          brief: {
            productName: 'Jacket',
            brandMode: 'generic',
            brandName: '',
            objective: '',
            audience: '',
            notes: '',
          },
          candidates: [
            { id: 'A', title: '干净街拍', summary: '城市街角', scene: '城市街角', behavior: '回身看镜头' },
            { id: 'B', title: '安静质感', summary: '明亮室内', scene: '明亮室内', behavior: '整理衣摆' },
            { id: 'C', title: '生活动作', summary: '生活化空间', scene: '生活化空间', behavior: '拿取随身物品' },
          ],
          selectedDirectionId: 'B',
        },
      },
    })

    const draft = draftFromPersistedDirectorProject(project, null)
    expect(draft.phase).toBe('directions')
    expect(draft.selectedDirectionId).toBe('B')
  })
})
