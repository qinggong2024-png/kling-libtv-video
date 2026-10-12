import { describe, expect, it } from 'vitest'
import type { StudioHandoffContext } from './contracts'
import {
  isProductionBridgePreparation,
  prepareProductionBridge,
} from './productionBridge'

const handoff: StudioHandoffContext = {
  source: 'director-studio',
  projectId: 'project-1',
  directionId: 'A',
  packageId: 'package-1',
  packageRevision: 3,
  shotId: 'FIRST_FRAME',
  references: {
    productFront: true,
    selectedDirection: true,
    productionPackage: true,
  },
}

describe('Production Bridge Preparation', () => {
  it('creates a read-only preflight context without a submission request', () => {
    const preparation = prepareProductionBridge(handoff)

    expect(preparation).toMatchObject({
      source: 'director-studio',
      purpose: 'VIDEO_DIRECTOR_FIXED',
      status: 'PREFLIGHT_REQUIRED',
      executionMode: 'OFFLINE_SYNTHETIC_ONLY',
      providerSubmissionAllowed: false,
      projectId: 'project-1',
      packageId: 'package-1',
      packageRevision: 3,
      shotId: 'FIRST_FRAME',
    })
    expect(preparation?.reality).toEqual({
      source: 'creative-intelligence-snapshot',
      mode: 'OFFLINE_SYNTHETIC_ONLY',
      status: 'PREFLIGHT_REQUIRED',
      snapshotId: null,
      snapshotRevision: null,
      dna: {
        characterDNAId: null,
        sceneDNAId: null,
        cameraDNAId: null,
        styleDNAId: null,
      },
    })
    expect(preparation?.checks).toEqual({
      ownerValidated: false,
      packageRevisionValidated: false,
      lockHashValidated: false,
      sourceHashValidated: false,
      qualificationValidated: false,
      licenseValidated: false,
      budgetValidated: false,
      authorizationValidated: false,
      executionStateValidated: false,
      materializedSourcesValidated: false,
    })
    expect(preparation?.nextSteps).toContain('HUMAN_PROVIDER_AUTHORIZATION_REQUIRED')
  })

  it('does not create a preparation context without a handoff', () => {
    expect(prepareProductionBridge(null)).toBeNull()
  })

  it('carries the existing CreativeIntelligenceSnapshot DNA mapping into preflight', () => {
    const preparation = prepareProductionBridge({
      ...handoff,
      intelligenceSnapshot: {
        realityEngineMode: 'OFFLINE_SYNTHETIC_ONLY',
        realitySnapshot: {
          id: 'reality-1',
          revision: 4,
          mode: 'OFFLINE_SYNTHETIC_ONLY',
          status: 'PREFLIGHT_REQUIRED',
          source: 'creative-project',
          characterDNA: {
            id: 'character-1',
            revision: 1,
            origin: 'USER_CONFIRMED',
            confidence: 0.9,
            identity: {},
            continuity: { appearance: [], wardrobe: [], behavior: [] },
            evidence: [],
            constraints: [],
          },
        },
      },
    })

    expect(preparation?.reality.snapshotId).toBe('reality-1')
    expect(preparation?.reality.snapshotRevision).toBe(4)
    expect(preparation?.reality.dna.characterDNAId).toBe('character-1')
    expect(preparation?.executionMode).toBe('OFFLINE_SYNTHETIC_ONLY')
    expect(preparation?.status).toBe('PREFLIGHT_REQUIRED')
    expect(preparation?.providerSubmissionAllowed).toBe(false)
  })

  it('recognizes only the explicitly non-submitting preparation shape', () => {
    expect(isProductionBridgePreparation(prepareProductionBridge(handoff))).toBe(true)
    expect(isProductionBridgePreparation({
      ...prepareProductionBridge(handoff),
      providerSubmissionAllowed: true,
    })).toBe(false)
    expect(isProductionBridgePreparation({ packageId: 'package-1' })).toBe(false)
  })
})
