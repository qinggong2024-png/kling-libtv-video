import { describe, expect, it } from 'vitest'
import { createCreativeProject } from './project'
import type { CreativeMemoryEntry } from './memory'
import {
  verifyOfflineCreativeOsFinalization,
  type OfflineFinalizationInput,
} from './offlineFinalization'

const memoryBase = {
  projectId: 'project-1',
  occurredAt: '2026-10-12T10:00:00.000Z',
  recordedAt: '2026-10-12T10:00:01.000Z',
  source: 'creative-project' as const,
}

function memoryEntries(): CreativeMemoryEntry[] {
  return [
    {
      ...memoryBase,
      id: 'direction-1',
      kind: 'direction-history',
      payload: { directionId: 'A', action: 'updated' as const },
    },
    {
      ...memoryBase,
      id: 'selection-1',
      kind: 'candidate-selection',
      payload: { candidateId: 'candidate-1', decision: 'selected' as const },
    },
    {
      ...memoryBase,
      id: 'package-1',
      kind: 'production-package-revision',
      payload: { packageId: 'package-1', revision: 1, parentPackageId: null },
    },
    {
      ...memoryBase,
      id: 'bridge-1',
      kind: 'bridge-decision',
      payload: {
        packageId: 'package-1',
        packageRevision: 1,
        decision: 'prepared' as const,
        purpose: 'IMAGE_FIRST_FRAME' as const,
        reasonCodes: ['PROVIDER_SUBMISSION_DISABLED'],
        providerSubmissionAllowed: false as const,
      },
    },
  ]
}

function completeInput(): OfflineFinalizationInput {
  return {
    project: createCreativeProject({
      id: 'project-1',
      assets: [{ id: 'product-1', kind: 'product', source: 'upload' }],
      metadata: {
        directorPlanning: {
          handoff: {
            source: 'director-studio',
            directionId: 'A',
            packageId: 'package-1',
            packageRevision: 1,
            shotId: 'FIRST_FRAME',
            references: {
              productFront: true,
              selectedDirection: true,
              productionPackage: true,
            },
          },
        },
      },
    }),
    imageResult: {
      id: 'fake-image-1',
      synthetic: true,
      providerSubmissionAllowed: false,
      qualificationScope: 'OFFLINE_SYNTHETIC_ONLY',
    },
    videoResult: {
      id: 'fake-video-1',
      synthetic: true,
      providerSubmissionAllowed: false,
      qualificationScope: 'OFFLINE_SYNTHETIC_ONLY',
    },
    qualityReview: {
      subjectId: 'fake-video-1',
      recommendation: 'QUALITY_REVIEW',
      evidenceRefs: ['synthetic-motion-check'],
      mode: 'OFFLINE_SYNTHETIC_ONLY',
    },
    memory: memoryEntries(),
  }
}

describe('offline Creative OS finalization verifier', () => {
  it('composes the existing boundaries into a complete offline workflow', () => {
    const result = verifyOfflineCreativeOsFinalization(completeInput())

    expect(result.blockingReasons).toEqual([])
    expect(result.completedStages).toEqual([
      'product-input',
      'director-studio',
      'production-package',
      'production-bridge-preflight',
      'image-studio',
      'video-studio',
      'quality-review',
      'creative-memory',
    ])
    expect(result.mode).toBe('OFFLINE_SYNTHETIC_ONLY')
    expect(result.preflightStatus).toBe('PREFLIGHT_REQUIRED')
    expect(result.providerSubmissionAllowed).toBe(false)
    expect(result.directorPackageId).toBe('package-1')
  })

  it('reports missing stages without changing project or task state', () => {
    const input = completeInput()
    const result = verifyOfflineCreativeOsFinalization({
      ...input,
      project: createCreativeProject({ id: 'empty-project', assets: [] }),
      imageResult: { ...input.imageResult, synthetic: false as true },
    })

    expect(result.completedStages).toEqual([
      'video-studio',
      'quality-review',
      'creative-memory',
    ])
    expect(result.blockingReasons).toEqual([
      'PRODUCT_INPUT_REQUIRED',
      'DIRECTOR_HANDOFF_REQUIRED',
      'PRODUCTION_PACKAGE_REQUIRED',
      'PRODUCTION_BRIDGE_PREFLIGHT_REQUIRED',
      'OFFLINE_IMAGE_RESULT_REQUIRED',
    ])
    expect('phase' in result).toBe(false)
    expect('task' in result).toBe(false)
  })
})
