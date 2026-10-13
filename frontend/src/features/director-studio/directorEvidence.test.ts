import { describe, expect, it } from 'vitest'
import type { DirectorTaskResponse } from './directorApi'
import { selectDirectorEvidence } from './directorEvidence'

const workflow = {
  id: 'task-1',
  status: 'PLAN_READY',
  state_version: 3,
  mode: 'OFFLINE_FAKE_ONLY',
  snapshot: {
    asset: {
      sha256: 'a'.repeat(64),
      object_key: 'creative-offline/product/front',
    },
    trace: [],
    candidates: [],
    calls: 0,
    cost_micros: 0,
    total_calls: 0,
    total_cost_micros: 0,
    plan: {
      claims: [{
        claim_id: 'front-source',
        value: 'front image available',
        source_fact_keys: ['source_asset_references'],
        evidence_kind: 'OBSERVED_REFERENCE',
        unknown_or_assumption: 'back view not observed',
      }],
    },
    package: {
      package_id: 'task-1:package:1',
      locks_hash: 'locks',
      preservation_hash: 'preservation',
      prompt: 'preserve the canonical product',
      reality: [
        { dimension: 'Camera', decision: 'eye-level', evidence: 'PROPOSED_FAKE' },
        { dimension: 'Lighting', decision: 'soft side light', evidence: 'PROPOSED_FAKE' },
        { dimension: 'Composition', decision: 'garment readable', evidence: 'PROPOSED_FAKE' },
        { dimension: 'Human Behavior', decision: 'standing still', evidence: 'PROPOSED_FAKE' },
        { dimension: 'Environment', decision: 'plain studio', evidence: 'PROPOSED_FAKE' },
        { dimension: 'Imperfection', decision: 'none', evidence: 'PROPOSED_FAKE' },
      ],
    },
    package_contracts: {
      'task-1:package:1': {
        text_contract: {
          contract_hash: 'contract',
          prompt_hash: 'prompt',
        },
        registry_snapshot: { version: 1 },
      },
    },
  },
} as unknown as DirectorTaskResponse

describe('director evidence projection', () => {
  it('exposes evidence without upgrading fake data to production qualification', () => {
    const evidence = selectDirectorEvidence(workflow)

    expect(evidence?.canonicalProduct).toEqual({
      sourceHash: 'a'.repeat(64),
      objectKey: 'creative-offline/product/front',
      availability: 'available',
    })
    expect(evidence?.backAssumption.value).toBe('back view not observed')
    expect(evidence?.groundedClaims[0].evidenceKind).toBe('OBSERVED_REFERENCE')
    expect(evidence?.reality).toHaveLength(6)
    expect(evidence?.textPackage).toMatchObject({
      prompt: 'preserve the canonical product',
      promptHash: 'prompt',
      locksHash: 'locks',
      preservationHash: 'preservation',
      contractHash: 'contract',
      registryVersion: 1,
      availability: 'available',
    })
  })

  it('keeps missing optional contracts explicit', () => {
    const withoutOptionalEvidence = {
      ...workflow,
      snapshot: {
        ...workflow.snapshot,
        package_contracts: undefined,
        text_contract: undefined,
        registry_snapshot: undefined,
      },
    } as unknown as DirectorTaskResponse

    const evidence = selectDirectorEvidence(withoutOptionalEvidence)

    expect(evidence?.textPackage.availability).toBe('available')
    expect(evidence?.textPackage.contractHash).toBeNull()
    expect(evidence?.backAssumption.availability).toBe('available')
  })

  it('returns no projection without an active task', () => {
    expect(selectDirectorEvidence(null)).toBeNull()
  })
})
