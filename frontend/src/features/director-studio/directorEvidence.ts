import type { DirectorTaskResponse } from './directorApi'

export const DIRECTOR_REALITY_DIMENSIONS = [
  'Camera',
  'Lighting',
  'Composition',
  'Human Behavior',
  'Environment',
  'Imperfection',
] as const

export type DirectorEvidenceAvailability = 'available' | 'unverified' | 'missing'

export interface DirectorEvidenceItem {
  key: string
  value: string
  availability: DirectorEvidenceAvailability
}

export interface DirectorEvidenceProjection {
  canonicalProduct: {
    sourceHash: string | null
    objectKey: string | null
    availability: DirectorEvidenceAvailability
  }
  backAssumption: DirectorEvidenceItem
  groundedClaims: Array<{
    claimId: string
    value: string
    sourceFactKeys: string[]
    evidenceKind: string
    unknownOrAssumption: string
    availability: DirectorEvidenceAvailability
  }>
  reality: Array<{
    dimension: string
    decision: string
    evidence: string
    availability: DirectorEvidenceAvailability
  }>
  textPackage: {
    prompt: string | null
    promptHash: string | null
    locksHash: string | null
    preservationHash: string | null
    contractHash: string | null
    registryVersion: number | null
    availability: DirectorEvidenceAvailability
  }
}

type LooseRecord = Record<string, unknown>

function record(value: unknown): LooseRecord {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as LooseRecord
    : {}
}

function stringValue(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string')
    : []
}

function availability(...values: unknown[]): DirectorEvidenceAvailability {
  return values.some((value) => typeof value === 'string' && value.trim())
    ? 'available'
    : 'missing'
}

function findPackageContract(snapshot: LooseRecord, packageId: string | null): LooseRecord {
  const contracts = record(snapshot.package_contracts)
  return packageId ? record(contracts[packageId]) : {}
}

export function selectDirectorEvidence(
  workflow: DirectorTaskResponse | null,
): DirectorEvidenceProjection | null {
  if (!workflow) return null

  const snapshot = record(workflow.snapshot)
  const asset = record(snapshot.asset)
  const productAssets = record(snapshot.product_assets)
  const backAsset = record(productAssets.back)
  const plan = record(snapshot.plan)
  const packageRevision = record(snapshot.package)
  const packageId = stringValue(packageRevision.package_id)
  const frozenContract = findPackageContract(snapshot, packageId)
  const textContract = record(frozenContract.text_contract ?? snapshot.text_contract)
  const registry = record(frozenContract.registry_snapshot ?? snapshot.registry_snapshot)

  const claims = Array.isArray(plan.claims) ? plan.claims : []
  const groundedClaims = claims.flatMap((claim, index) => {
    const item = record(claim)
    const value = stringValue(item.value)
    if (!value) return []
    return [{
      claimId: stringValue(item.claim_id) ?? `claim-${index + 1}`,
      value,
      sourceFactKeys: stringList(item.source_fact_keys),
      evidenceKind: stringValue(item.evidence_kind) ?? 'UNVERIFIED',
      unknownOrAssumption: stringValue(item.unknown_or_assumption) ?? '',
      availability: 'available' as const,
    }]
  })
  const backAssumption = groundedClaims.find((claim) =>
    /back|背面/i.test(`${claim.unknownOrAssumption} ${claim.value}`),
  )

  const realitySource = Array.isArray(packageRevision.reality) ? packageRevision.reality : []
  const realityByDimension = new Map(
    realitySource.map((entry) => {
      const item = record(entry)
      return [stringValue(item.dimension) ?? '', item]
    }),
  )
  const reality = DIRECTOR_REALITY_DIMENSIONS.map((dimension) => {
    const item = realityByDimension.get(dimension) ?? {}
    return {
      dimension,
      decision: stringValue(item.decision) ?? '',
      evidence: stringValue(item.evidence) ?? '',
      availability: availability(item.decision, item.evidence),
    }
  })

  const prompt = stringValue(packageRevision.prompt)
  const promptHash = stringValue(textContract.prompt_hash)
  const locksHash = stringValue(packageRevision.locks_hash)
  const preservationHash = stringValue(packageRevision.preservation_hash)
  const contractHash = stringValue(textContract.contract_hash)
  const registryVersion = typeof registry.version === 'number' ? registry.version : null

  return {
    canonicalProduct: {
      sourceHash: stringValue(asset.sha256),
      objectKey: stringValue(asset.object_key),
      availability: availability(asset.sha256, asset.object_key),
    },
    backAssumption: {
      key: 'back-view',
      value: backAsset.object_key
        ? 'back view available from uploaded reference'
        : backAssumption?.unknownOrAssumption || 'back view not observed',
      availability: backAsset.object_key || backAssumption ? 'available' : 'unverified',
    },
    groundedClaims,
    reality,
    textPackage: {
      prompt,
      promptHash,
      locksHash,
      preservationHash,
      contractHash,
      registryVersion,
      availability: availability(
        prompt,
        promptHash,
        locksHash,
        preservationHash,
        contractHash,
        registryVersion,
      ),
    },
  }
}
