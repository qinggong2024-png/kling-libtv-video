import { describe, expect, it } from 'vitest'
import type { StudioHandoffContext } from './contracts'
import { createCreativeProject } from '../../creative-project/project'
import {
  DIRECTOR_FIXED_OFFLINE_INPUT_SCHEMA_VERSION,
  PRODUCTION_BRIDGE_PREFLIGHT_SCHEMA_VERSION,
  PRODUCTION_BRIDGE_QUALIFICATION_SCOPE,
  isProductionBridgePreparation,
  prepareDirectorFixedOffline,
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
      executionMode: 'OFFLINE_SYNTHETIC_ONLY',
      providerSubmissionAllowed: false,
      qualificationScope: PRODUCTION_BRIDGE_QUALIFICATION_SCOPE,
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
    expect(isProductionBridgePreparation({
      ...prepareProductionBridge(handoff),
      preflight: {
        ...prepareProductionBridge(handoff)?.preflight,
        mode: 'SUBMIT',
      },
    })).toBe(false)
    expect(isProductionBridgePreparation({ packageId: 'package-1' })).toBe(false)
  })

  it('adapts immutable director metadata into a read-only director_fixed input', () => {
    const project = createCreativeProject({
      id: 'project-1',
      workflowContext: { creativeTaskId: 'creative-task-1' },
      metadata: {
        directorPlanning: {
          selectedDirectionId: 'B',
          handoff,
          directorFixed: {
            packageId: 'storyboard-package-1',
            packageRevision: 4,
            shotId: 'SHOT_01',
            candidateId: 'storyboard-candidate-1',
            sourceImageHash: 'a'.repeat(64),
            shotMapping: {
              shotId: 'SHOT_01',
              candidateId: 'storyboard-candidate-1',
              outputId: 'output-1',
              outputImageHash: 'b'.repeat(64),
              objectKey: 'fake://output-1',
            },
            package: {
              locksHash: 'locks-4',
              preservationHash: 'preservation-4',
              factsRevision: 2,
            },
          },
        },
      },
    })

    const preparation = prepareDirectorFixedOffline(project)

    expect(preparation).toMatchObject({
      schemaVersion: DIRECTOR_FIXED_OFFLINE_INPUT_SCHEMA_VERSION,
      mode: 'READ_ONLY',
      status: 'READY',
      providerSubmissionAllowed: false,
      input: {
        executionMode: 'director_fixed',
        creativeTaskId: 'creative-task-1',
        packageId: 'storyboard-package-1',
        packageRevision: 4,
        shotId: 'SHOT_01',
        candidateId: 'storyboard-candidate-1',
        sourceImageHash: 'a'.repeat(64),
        shotMapping: {
          outputId: 'output-1',
          outputImageHash: 'b'.repeat(64),
        },
        immutableSummary: {
          directionId: 'B',
          locksHash: 'locks-4',
          preservationHash: 'preservation-4',
          factsRevision: 2,
        },
      },
    })
    expect(Object.isFrozen(preparation?.input)).toBe(true)
    expect(preparation?.missingFields).toEqual([])
  })

  it('rebuilds director_fixed from complete persisted metadata when reload removed the handoff File context', () => {
    const sourceImageHash = 'a'.repeat(64)
    const project = createCreativeProject({
      id: 'project-1',
      metadata: {
        directorPlanning: {
          handoff: null,
          directorFixed: {
            creativeTaskId: 'creative-task-1',
            package: {
              package_id: 'storyboard-package-1',
              revision: 4,
              shot_id: 'SHOT_01',
            },
            selection: {
              candidate_id: 'storyboard-candidate-1',
              package_id: 'storyboard-package-1',
              shot_id: 'SHOT_01',
            },
            sourceImageHash,
            shotMapping: {
              shot_id: 'SHOT_01',
              package_id: 'storyboard-package-1',
              candidate_id: 'storyboard-candidate-1',
              source_image_hash: sourceImageHash,
              output_id: 'storyboard-candidate-1-output',
              object_key: 'offline/storyboard-candidate-1.png',
            },
          },
        },
      },
    })

    const preparation = prepareDirectorFixedOffline(project)

    expect(preparation).toMatchObject({
      status: 'READY',
      creativeTaskId: 'creative-task-1',
      packageId: 'storyboard-package-1',
      packageRevision: 4,
      shotId: 'SHOT_01',
      candidateId: 'storyboard-candidate-1',
      sourceImageHash,
      shotMapping: {
        outputId: 'storyboard-candidate-1-output',
      },
      input: {
        source: 'director-studio',
        executionMode: 'director_fixed',
        qualificationScope: 'OFFLINE_SYNTHETIC_ONLY',
        providerSubmissionAllowed: false,
        deliverableEligible: false,
      },
    })
  })

  it('rebuilds director_fixed from an offline source image identifier', () => {
    const sourceImageHash = 'source-image-hash-1'
    const project = createCreativeProject({
      id: 'project-1',
      metadata: {
        directorPlanning: {
          handoff: null,
          directorFixed: {
            creative_task_id: 'creative-task-1',
            package: {
              package_id: 'storyboard-package-1',
              revision: 4,
              shot_id: 'SHOT_01',
            },
            selection: {
              candidate_id: 'storyboard-candidate-1',
              package_id: 'storyboard-package-1',
              shot_id: 'SHOT_01',
            },
            source_image_hash: sourceImageHash,
            shotMapping: {
              shot_id: 'SHOT_01',
              package_id: 'storyboard-package-1',
              candidate_id: 'storyboard-candidate-1',
              source_image_hash: sourceImageHash,
              output_id: 'storyboard-candidate-1-output',
              output_sha256: 'not-a-sha256',
              object_key: 'offline/storyboard-candidate-1.png',
            },
          },
        },
      },
    })

    const preparation = prepareDirectorFixedOffline(project)

    expect(preparation).toMatchObject({
      status: 'READY',
      sourceImageHash,
      shotMapping: {
        sourceImageHash,
        outputId: 'storyboard-candidate-1-output',
        objectKey: 'offline/storyboard-candidate-1.png',
      },
      input: {
        executionMode: 'director_fixed',
        qualificationScope: 'OFFLINE_SYNTHETIC_ONLY',
        providerSubmissionAllowed: false,
        deliverableEligible: false,
      },
      missingFields: [],
    })
    expect(preparation?.shotMapping?.outputImageHash).toBeUndefined()
  })

  it('keeps the Video Studio preparation blocked when the immutable shot mapping is absent', () => {
    const project = createCreativeProject({
      id: 'project-1',
      workflowContext: { creativeTaskId: 'creative-task-1' },
      metadata: {
        directorPlanning: {
          selectedDirectionId: 'A',
          handoff,
        },
      },
    })

    expect(prepareDirectorFixedOffline(project)).toMatchObject({
      status: 'BLOCKED',
      creativeTaskId: 'creative-task-1',
      packageId: 'package-1',
      packageRevision: 3,
      shotId: null,
      candidateId: null,
      sourceImageHash: null,
      missingFields: [
        'shot_id=SHOT_01',
        'candidate_id',
        'source_image_hash',
        'shot_mapping',
      ],
      input: null,
    })
  })
})
