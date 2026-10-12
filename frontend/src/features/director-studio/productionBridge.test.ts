import { describe, expect, it } from 'vitest'
import type { StudioHandoffContext } from './contracts'
import {
  PRODUCTION_BRIDGE_PREFLIGHT_SCHEMA_VERSION,
  PRODUCTION_BRIDGE_QUALIFICATION_SCOPE,
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
      schemaVersion: PRODUCTION_BRIDGE_PREFLIGHT_SCHEMA_VERSION,
      source: 'director-studio',
      purpose: 'VIDEO_DIRECTOR_FIXED',
      status: 'PREFLIGHT_REQUIRED',
      providerSubmissionAllowed: false,
      qualificationScope: PRODUCTION_BRIDGE_QUALIFICATION_SCOPE,
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
    expect(preparation?.preflight).toMatchObject({
      schemaVersion: PRODUCTION_BRIDGE_PREFLIGHT_SCHEMA_VERSION,
      mode: 'READ_ONLY',
      status: 'PREFLIGHT_REQUIRED',
      qualificationScope: PRODUCTION_BRIDGE_QUALIFICATION_SCOPE,
      providerSubmissionAllowed: false,
      readiness: {
        score: 0,
        maxScore: 100,
        validatedChecks: 0,
        totalChecks: 10,
        blockingChecks: 10,
        state: 'NOT_READY',
      },
      approvalCheckpoint: {
        id: 'CHECKPOINT_1',
        status: 'REQUIRED',
        required: true,
        decision: 'PENDING',
        scope: 'PRODUCTION_BRIDGE_CONTRACT_REVIEW',
      },
    })
    expect(preparation?.preflight.checkResults).toHaveLength(10)
    expect(preparation?.blockingReasons.map((reason) => reason.code)).toEqual([
      'FRONTEND_HANDOFF_ONLY',
      'HUMAN_CHECKPOINT_1_REQUIRED',
      'OFFLINE_SYNTHETIC_ONLY',
      'PROVIDER_SUBMISSION_DISABLED',
      'OWNER_VALIDATION_REQUIRED',
      'PACKAGE_REVISION_VALIDATION_REQUIRED',
      'LOCK_HASH_VALIDATION_REQUIRED',
      'SOURCE_HASH_VALIDATION_REQUIRED',
      'QUALIFICATION_VALIDATION_REQUIRED',
      'LICENSE_VALIDATION_REQUIRED',
      'BUDGET_VALIDATION_REQUIRED',
      'AUTHORIZATION_VALIDATION_REQUIRED',
      'EXECUTION_STATE_VALIDATION_REQUIRED',
      'MATERIALIZED_SOURCE_MAPPING_REQUIRED',
    ])
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
    expect(isProductionBridgePreparation({
      ...prepareProductionBridge(handoff),
      preflight: {
        ...prepareProductionBridge(handoff)?.preflight,
        mode: 'SUBMIT',
      },
    })).toBe(false)
    expect(isProductionBridgePreparation({ packageId: 'package-1' })).toBe(false)
  })
})
