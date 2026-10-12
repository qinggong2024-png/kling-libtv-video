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
      providerSubmissionAllowed: false,
      projectId: 'project-1',
      packageId: 'package-1',
      packageRevision: 3,
      shotId: 'FIRST_FRAME',
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

  it('recognizes only the explicitly non-submitting preparation shape', () => {
    expect(isProductionBridgePreparation(prepareProductionBridge(handoff))).toBe(true)
    expect(isProductionBridgePreparation({
      ...prepareProductionBridge(handoff),
      providerSubmissionAllowed: true,
    })).toBe(false)
    expect(isProductionBridgePreparation({ packageId: 'package-1' })).toBe(false)
  })
})
