import { describe, expect, it } from 'vitest'
import {
  createMotionReferencePlaceholder,
  isOfflineSpatialContract,
  toSpatialDNA,
} from './spatialAdapters'

describe('spatial understanding preparation contracts', () => {
  it('normalizes spatial observations without enabling execution', () => {
    const spatial = toSpatialDNA({
      referenceId: '  image-1 ',
      depthReferences: [{
        entityId: 'subject',
        depthBand: 'FOREGROUND',
        confidence: 0.8,
        source: 'HUMAN_ANNOTATION',
      }],
      cameraRelationships: [{
        cameraId: 'camera-1',
        subjectId: 'subject',
        relationship: 'THREE_QUARTER',
        framing: 'MEDIUM',
      }],
    })

    expect(spatial.referenceId).toBe('image-1')
    expect(spatial.depthReferences[0].schemaVersion).toBe('depth-reference.v1')
    expect(spatial.cameraRelationships[0].schemaVersion).toBe('camera-relationship.v1')
    expect(isOfflineSpatialContract(spatial)).toBe(true)
  })

  it('creates a non-executable motion placeholder', () => {
    const placeholder = createMotionReferencePlaceholder(
      'motion-1',
      'WEIGHT_SHIFT',
      'A small natural weight shift',
    )

    expect(placeholder).toMatchObject({
      schemaVersion: 'motion-reference-placeholder.v1',
      mode: 'OFFLINE_SYNTHETIC_ONLY',
      preflightStatus: 'PREFLIGHT_REQUIRED',
      providerSubmissionAllowed: false,
      source: 'SYNTHETIC_PLACEHOLDER',
    })
  })

  it('rejects a contract that could submit to a provider', () => {
    expect(isOfflineSpatialContract({
      mode: 'OFFLINE_SYNTHETIC_ONLY',
      preflightStatus: 'PREFLIGHT_REQUIRED',
      providerSubmissionAllowed: true,
    })).toBe(false)
  })
})
