import type { StudioHandoffContext } from './contracts'
import type { CreativeProject } from '../../creative-project/types'
import { readDirectorPlanningSnapshot } from './directorHandoff'
import { mapCreativeIntelligenceSnapshotToReality } from '../../creative-project/realityAdapters'
import type { RealityEngineExecutionMode, RealitySnapshotMapping } from '../../creative-project/reality'

export const PRODUCTION_BRIDGE_PREFLIGHT_SCHEMA_VERSION = 'production-bridge-preflight.v1' as const
export const PRODUCTION_BRIDGE_QUALIFICATION_SCOPE = 'OFFLINE_SYNTHETIC_ONLY' as const
export const DIRECTOR_FIXED_OFFLINE_INPUT_SCHEMA_VERSION = 'director-fixed-offline.v1' as const

export type ProductionBridgePurpose = 'IMAGE_FIRST_FRAME' | 'VIDEO_DIRECTOR_FIXED'
export type ProductionBridgePreparationStatus = 'PLANNING_ONLY' | 'PREFLIGHT_REQUIRED'
export type ProductionBridgeCheckStatus = 'UNVERIFIED' | 'PASS' | 'BLOCKED'
export type ProductionBridgeReadinessState = 'NOT_READY' | 'READY_FOR_HUMAN_CHECKPOINT'
export type ProductionBridgeApprovalStatus = 'REQUIRED' | 'ACCEPTED' | 'REJECTED'
export type DirectorFixedOfflinePreparationStatus = 'READY' | 'BLOCKED'

export type ProductionBridgeCheckKey =
  | 'ownerValidated'
  | 'packageRevisionValidated'
  | 'lockHashValidated'
  | 'sourceHashValidated'
  | 'qualificationValidated'
  | 'licenseValidated'
  | 'budgetValidated'
  | 'authorizationValidated'
  | 'executionStateValidated'
  | 'materializedSourcesValidated'

export type ProductionBridgeBlockingReasonCode =
  | 'FRONTEND_HANDOFF_ONLY'
  | 'OWNER_VALIDATION_REQUIRED'
  | 'PACKAGE_REVISION_VALIDATION_REQUIRED'
  | 'LOCK_HASH_VALIDATION_REQUIRED'
  | 'SOURCE_HASH_VALIDATION_REQUIRED'
  | 'QUALIFICATION_VALIDATION_REQUIRED'
  | 'LICENSE_VALIDATION_REQUIRED'
  | 'BUDGET_VALIDATION_REQUIRED'
  | 'AUTHORIZATION_VALIDATION_REQUIRED'
  | 'EXECUTION_STATE_VALIDATION_REQUIRED'
  | 'MATERIALIZED_SOURCE_MAPPING_REQUIRED'
  | 'HUMAN_CHECKPOINT_1_REQUIRED'
  | 'OFFLINE_SYNTHETIC_ONLY'
  | 'PROVIDER_SUBMISSION_DISABLED'

export type ProductionBridgeBlockingReasonCategory =
  | 'CONTEXT'
  | 'OWNERSHIP'
  | 'PACKAGE_INTEGRITY'
  | 'SOURCE_PROVENANCE'
  | 'QUALIFICATION'
  | 'LICENSE'
  | 'BUDGET'
  | 'AUTHORIZATION'
  | 'EXECUTION_STATE'
  | 'HUMAN_APPROVAL'
  | 'EXECUTION_POLICY'
export type ProductionBridgeExecutionMode = RealityEngineExecutionMode

export interface ProductionBridgeChecks {
  ownerValidated: boolean
  packageRevisionValidated: boolean
  lockHashValidated: boolean
  sourceHashValidated: boolean
  qualificationValidated: boolean
  licenseValidated: boolean
  budgetValidated: boolean
  authorizationValidated: boolean
  executionStateValidated: boolean
  materializedSourcesValidated: boolean
}

export interface ProductionBridgeCheckResult {
  key: ProductionBridgeCheckKey
  status: ProductionBridgeCheckStatus
  category: ProductionBridgeBlockingReasonCategory
  serverEvidenceRequired: true
}

export interface ProductionBridgeBlockingReason {
  code: ProductionBridgeBlockingReasonCode
  category: ProductionBridgeBlockingReasonCategory
  severity: 'BLOCKING'
  message: string
}

export interface ProductionBridgeReadiness {
  score: number
  maxScore: 100
  validatedChecks: number
  totalChecks: number
  blockingChecks: number
  state: ProductionBridgeReadinessState
}

export interface ProductionBridgeApprovalCheckpoint {
  id: 'CHECKPOINT_1'
  status: ProductionBridgeApprovalStatus
  required: true
  decision: 'PENDING' | 'ACCEPTED' | 'REJECTED'
  scope: 'PRODUCTION_BRIDGE_CONTRACT_REVIEW'
}

export interface ProductionBridgePreflightResult {
  schemaVersion: typeof PRODUCTION_BRIDGE_PREFLIGHT_SCHEMA_VERSION
  mode: 'READ_ONLY'
  status: 'PREFLIGHT_REQUIRED'
  qualificationScope: typeof PRODUCTION_BRIDGE_QUALIFICATION_SCOPE
  providerSubmissionAllowed: false
  checkResults: ProductionBridgeCheckResult[]
  readiness: ProductionBridgeReadiness
  approvalCheckpoint: ProductionBridgeApprovalCheckpoint
}

export interface ProductionBridgePreparation {
  schemaVersion: typeof PRODUCTION_BRIDGE_PREFLIGHT_SCHEMA_VERSION
  source: 'director-studio'
  purpose: ProductionBridgePurpose
  status: ProductionBridgePreparationStatus
  executionMode: ProductionBridgeExecutionMode
  providerSubmissionAllowed: false
  qualificationScope: typeof PRODUCTION_BRIDGE_QUALIFICATION_SCOPE
  projectId?: string
  directionId: StudioHandoffContext['directionId']
  packageId: string
  packageRevision: number
  shotId: StudioHandoffContext['shotId']
  checks: ProductionBridgeChecks
  blockingReasons: ProductionBridgeBlockingReason[]
  preflight: ProductionBridgePreflightResult
  reality: RealitySnapshotMapping
  nextSteps: [
    'SERVER_VALIDATED_PACKAGE_REQUIRED',
    'MATERIALIZED_SOURCE_MAPPING_REQUIRED',
    'HUMAN_PROVIDER_AUTHORIZATION_REQUIRED',
  ]
}

export interface DirectorFixedShotMapping {
  shotId: 'SHOT_01'
  order: 1
  packageId: string
  candidateId: string
  sourceImageHash: string
  batchId?: string
  itemId?: string
  outputId?: string
  outputImageHash?: string
  objectKey?: string
}

export interface DirectorFixedOfflineInput {
  schemaVersion: typeof DIRECTOR_FIXED_OFFLINE_INPUT_SCHEMA_VERSION
  source: 'director-studio'
  executionMode: 'director_fixed'
  qualificationScope: typeof PRODUCTION_BRIDGE_QUALIFICATION_SCOPE
  providerSubmissionAllowed: false
  deliverableEligible: false
  offlineSyntheticOnly: true
  creativeTaskId: string
  packageId: string
  packageRevision: number
  shotId: 'SHOT_01'
  candidateId: string
  sourceImageHash: string
  shotMapping: DirectorFixedShotMapping
  immutableSummary: {
    directionId: StudioHandoffContext['directionId']
    locksHash?: string
    preservationHash?: string
    factsRevision?: number
  }
}

export interface DirectorFixedOfflinePreparation {
  schemaVersion: typeof DIRECTOR_FIXED_OFFLINE_INPUT_SCHEMA_VERSION
  mode: 'READ_ONLY'
  status: DirectorFixedOfflinePreparationStatus
  providerSubmissionAllowed: false
  qualificationScope: typeof PRODUCTION_BRIDGE_QUALIFICATION_SCOPE
  input: DirectorFixedOfflineInput | null
  creativeTaskId: string | null
  packageId: string | null
  packageRevision: number | null
  shotId: 'SHOT_01' | null
  candidateId: string | null
  sourceImageHash: string | null
  shotMapping: DirectorFixedShotMapping | null
  missingFields: string[]
  preflight: ProductionBridgePreflightResult | null
}

const checkDefinitions: ReadonlyArray<{
  key: ProductionBridgeCheckKey
  category: ProductionBridgeBlockingReasonCategory
  code: ProductionBridgeBlockingReasonCode
  message: string
}> = [
  {
    key: 'ownerValidated',
    category: 'OWNERSHIP',
    code: 'OWNER_VALIDATION_REQUIRED',
    message: '需要服务端重新校验 CreativeProject owner 与当前登录主体。',
  },
  {
    key: 'packageRevisionValidated',
    category: 'PACKAGE_INTEGRITY',
    code: 'PACKAGE_REVISION_VALIDATION_REQUIRED',
    message: '需要服务端重新校验 Production Package revision 仍为当前版本。',
  },
  {
    key: 'lockHashValidated',
    category: 'PACKAGE_INTEGRITY',
    code: 'LOCK_HASH_VALIDATION_REQUIRED',
    message: '需要服务端重新校验 package lock hash 与不可变锁项。',
  },
  {
    key: 'sourceHashValidated',
    category: 'SOURCE_PROVENANCE',
    code: 'SOURCE_HASH_VALIDATION_REQUIRED',
    message: '需要服务端重新校验 materialized source 的对象和字节哈希。',
  },
  {
    key: 'qualificationValidated',
    category: 'QUALIFICATION',
    code: 'QUALIFICATION_VALIDATION_REQUIRED',
    message: '当前候选仍是 OFFLINE_SYNTHETIC_ONLY，不能作为生产资格证据。',
  },
  {
    key: 'licenseValidated',
    category: 'LICENSE',
    code: 'LICENSE_VALIDATION_REQUIRED',
    message: '需要服务端提供真实来源与使用许可证据。',
  },
  {
    key: 'budgetValidated',
    category: 'BUDGET',
    code: 'BUDGET_VALIDATION_REQUIRED',
    message: '需要服务端重新校验预算、报价和当前额度证据。',
  },
  {
    key: 'authorizationValidated',
    category: 'AUTHORIZATION',
    code: 'AUTHORIZATION_VALIDATION_REQUIRED',
    message: '需要人工 Provider authorization evidence，当前未允许提交。',
  },
  {
    key: 'executionStateValidated',
    category: 'EXECUTION_STATE',
    code: 'EXECUTION_STATE_VALIDATION_REQUIRED',
    message: '需要服务端重新校验当前 CreativeProject / package execution state。',
  },
  {
    key: 'materializedSourcesValidated',
    category: 'SOURCE_PROVENANCE',
    code: 'MATERIALIZED_SOURCE_MAPPING_REQUIRED',
    message: '需要服务端提供 materialized source mappings，前端 handoff 不包含可提交媒体。',
  },
]

const preflightChecks: ProductionBridgeChecks = {
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
}

function createBlockingReason(
  code: ProductionBridgeBlockingReasonCode,
  category: ProductionBridgeBlockingReasonCategory,
  message: string,
): ProductionBridgeBlockingReason {
  return { code, category, severity: 'BLOCKING', message }
}

function createPreflightResult(
  checks: ProductionBridgeChecks,
): {
  preflight: ProductionBridgePreflightResult
  blockingReasons: ProductionBridgeBlockingReason[]
} {
  const checkResults = checkDefinitions.map((definition) => ({
    key: definition.key,
    status: (checks[definition.key] ? 'PASS' : 'UNVERIFIED') as ProductionBridgeCheckStatus,
    category: definition.category,
    serverEvidenceRequired: true as const,
  }))
  const validatedChecks = checkResults.filter((check) => check.status === 'PASS').length
  const totalChecks = checkResults.length
  const blockingChecks = totalChecks - validatedChecks
  const blockingReasons = checkDefinitions
    .filter((definition) => !checks[definition.key])
    .map((definition) => createBlockingReason(
      definition.code,
      definition.category,
      definition.message,
    ))

  blockingReasons.unshift(
    createBlockingReason(
      'FRONTEND_HANDOFF_ONLY',
      'CONTEXT',
      '当前 handoff 只读且来自前端上下文，不代表服务端已完成 preflight。',
    ),
    createBlockingReason(
      'HUMAN_CHECKPOINT_1_REQUIRED',
      'HUMAN_APPROVAL',
      '需要人工 Checkpoint 1 确认是否进入 production bridge contract review。',
    ),
    createBlockingReason(
      'OFFLINE_SYNTHETIC_ONLY',
      'QUALIFICATION',
      '当前范围固定为 OFFLINE_SYNTHETIC_ONLY，不具备普通 QUALIFIED 或 Deliverable 资格。',
    ),
    createBlockingReason(
      'PROVIDER_SUBMISSION_DISABLED',
      'EXECUTION_POLICY',
      '当前只读准备阶段禁止 Provider submission、真实任务创建和生产执行。',
    ),
  )

  return {
    preflight: {
      schemaVersion: PRODUCTION_BRIDGE_PREFLIGHT_SCHEMA_VERSION,
      mode: 'READ_ONLY',
      status: 'PREFLIGHT_REQUIRED',
      qualificationScope: PRODUCTION_BRIDGE_QUALIFICATION_SCOPE,
      providerSubmissionAllowed: false,
      checkResults,
      readiness: {
        score: Math.round((validatedChecks / totalChecks) * 100),
        maxScore: 100,
        validatedChecks,
        totalChecks,
        blockingChecks,
        state: blockingChecks === 0 ? 'READY_FOR_HUMAN_CHECKPOINT' : 'NOT_READY',
      },
      approvalCheckpoint: {
        id: 'CHECKPOINT_1',
        status: 'REQUIRED',
        required: true,
        decision: 'PENDING',
        scope: 'PRODUCTION_BRIDGE_CONTRACT_REVIEW',
      },
    },
    blockingReasons,
  }
}

type UnknownRecord = Record<string, unknown>

function asRecord(value: unknown): UnknownRecord | null {
  return typeof value === 'object' && value !== null ? value as UnknownRecord : null
}

function nonEmptyString(...values: unknown[]): string | null {
  return values.find((value): value is string => typeof value === 'string' && value.trim().length > 0)?.trim() ?? null
}

function positiveNumber(...values: unknown[]): number | null {
  return values.find((value): value is number => typeof value === 'number' && Number.isFinite(value) && value > 0) ?? null
}

function sha256(value: unknown): string | null {
  return typeof value === 'string' && /^[0-9a-f]{64}$/i.test(value) ? value.toLowerCase() : null
}

function sourceImageIdentifier(value: unknown): string | null {
  return nonEmptyString(value)
}

function freezeDirectorFixedInput(input: DirectorFixedOfflineInput): DirectorFixedOfflineInput {
  Object.freeze(input.immutableSummary)
  Object.freeze(input.shotMapping)
  return Object.freeze(input)
}

function directorFixedPlanningRecords(project: CreativeProject): {
  planning: UnknownRecord
  handoff: UnknownRecord
  fixed: UnknownRecord
  storyboard: UnknownRecord
  selection: UnknownRecord
  mapping: UnknownRecord
} | null {
  const planning = asRecord(project.metadata?.directorPlanning)
  if (!planning) return null
  const persistedHandoff = asRecord(planning.handoff)
  const fixedMetadata = asRecord(planning.directorFixed)
    ?? asRecord(planning.videoHandoff)
    ?? asRecord(persistedHandoff?.directorFixed)
  if (persistedHandoff && persistedHandoff.source !== 'director-studio') return null
  if (!persistedHandoff && !fixedMetadata) return null
  const handoff = persistedHandoff ?? {}
  const fixed = fixedMetadata ?? {}
  const storyboard = asRecord(fixed.storyboard)
    ?? asRecord(planning.storyboard)
    ?? {}
  const selections = asRecord(storyboard.selections)
  const selection = asRecord(fixed.selection)
    ?? asRecord(selections?.SHOT_01)
    ?? asRecord(planning.selection)
    ?? {}
  const mappings = asRecord(storyboard.shotMappings)
    ?? asRecord(storyboard.shot_mappings)
    ?? asRecord(fixed.shotMappings)
    ?? asRecord(fixed.shot_mappings)
  const mapping = asRecord(fixed.shotMapping)
    ?? asRecord(handoff.shotMapping)
    ?? asRecord(planning.shotMapping)
    ?? asRecord(mappings?.SHOT_01)
    ?? {}
  return { planning, handoff, fixed, storyboard, selection, mapping }
}

export function prepareDirectorFixedOffline(
  project: CreativeProject | null,
): DirectorFixedOfflinePreparation | null {
  if (!project) return null
  const records = directorFixedPlanningRecords(project)
  if (!records) return null
  const { planning, handoff, fixed, storyboard, selection, mapping } = records
  const snapshot = readDirectorPlanningSnapshot(project)
  const rootPackage = asRecord(planning.productionPackage)
  const storyboardPackage = asRecord(fixed.package)
    ?? asRecord(fixed.packageRevision)
    ?? asRecord(storyboard.package)
    ?? asRecord(asRecord(storyboard.packages)?.SHOT_01)
    ?? (handoff.packageId
      ? {
          packageId: handoff.packageId,
          packageRevision: handoff.packageRevision,
          shotId: handoff.shotId,
        }
      : null)
  const creativeTaskId = nonEmptyString(
    fixed.creativeTaskId,
    fixed.creative_task_id,
    handoff.creativeTaskId,
    handoff.creative_task_id,
    planning.creativeTaskId,
    planning.creative_task_id,
    project.metadata?.creativeTaskId,
    project.workflowContext?.activeTaskId,
    project.workflowContext?.creativeTaskId,
  )
  const packageId = nonEmptyString(
    fixed.packageId,
    fixed.package_id,
    storyboardPackage?.packageId,
    storyboardPackage?.package_id,
    handoff.packageId,
    handoff.package_id,
  )
  const packageRevision = positiveNumber(
    fixed.packageRevision,
    fixed.package_revision,
    storyboardPackage?.revision,
    handoff.packageRevision,
    handoff.package_revision,
  )
  const shotId = nonEmptyString(
    fixed.shotId,
    fixed.shot_id,
    storyboardPackage?.shotId,
    storyboardPackage?.shot_id,
    mapping.shotId,
    mapping.shot_id,
  ) === 'SHOT_01' ? 'SHOT_01' as const : null
  const candidateId = nonEmptyString(
    fixed.candidateId,
    fixed.candidate_id,
    fixed.selectedCandidateId,
    fixed.selected_candidate_id,
    selection.candidateId,
    selection.candidate_id,
    mapping.candidateId,
    mapping.candidate_id,
  )
  const sourceImageHash = sourceImageIdentifier(
    fixed.sourceImageHash
      ?? fixed.source_image_hash
      ?? fixed.source_sha256
      ?? mapping.sourceImageHash
      ?? mapping.source_image_hash
      ?? mapping.source_sha256
      ?? planning.sourceImageHash
      ?? planning.source_image_hash
      ?? planning.source_sha256
      ?? asRecord(planning.asset)?.sha256
      ?? asRecord(planning.asset)?.source_image_hash
      ?? asRecord(asRecord(project.metadata?.directorRecovery)?.product_reference)?.source_sha256
      ?? project.assets.find((asset) => asset.kind === 'product')?.metadata?.sha256,
  )
  const normalizedMapping = packageId && candidateId && sourceImageHash
    ? {
        shotId: 'SHOT_01' as const,
        order: 1 as const,
        packageId,
        candidateId,
        sourceImageHash,
        ...(nonEmptyString(mapping.batchId, mapping.batch_id) ? { batchId: nonEmptyString(mapping.batchId, mapping.batch_id)! } : {}),
        ...(nonEmptyString(mapping.itemId, mapping.item_id) ? { itemId: nonEmptyString(mapping.itemId, mapping.item_id)! } : {}),
        ...(nonEmptyString(mapping.outputId, mapping.output_id) ? { outputId: nonEmptyString(mapping.outputId, mapping.output_id)! } : {}),
        ...(sha256(mapping.outputImageHash ?? mapping.output_sha256) ? { outputImageHash: sha256(mapping.outputImageHash ?? mapping.output_sha256)! } : {}),
        ...(nonEmptyString(mapping.objectKey, mapping.object_key) ? { objectKey: nonEmptyString(mapping.objectKey, mapping.object_key)! } : {}),
      }
    : null
  const missingFields = [
    !creativeTaskId ? 'creative_task_id' : '',
    !packageId ? 'package_id' : '',
    !packageRevision ? 'package_revision' : '',
    !shotId ? 'shot_id=SHOT_01' : '',
    !candidateId ? 'candidate_id' : '',
    !sourceImageHash ? 'source_image_hash' : '',
    !normalizedMapping ? 'shot_mapping' : '',
  ].filter(Boolean)
  const input = !missingFields.length && normalizedMapping
    ? freezeDirectorFixedInput({
        schemaVersion: DIRECTOR_FIXED_OFFLINE_INPUT_SCHEMA_VERSION,
        source: 'director-studio',
        executionMode: 'director_fixed',
        qualificationScope: PRODUCTION_BRIDGE_QUALIFICATION_SCOPE,
        providerSubmissionAllowed: false,
        deliverableEligible: false,
        offlineSyntheticOnly: true,
        creativeTaskId: creativeTaskId!,
        packageId: packageId!,
        packageRevision: packageRevision!,
        shotId: 'SHOT_01',
        candidateId: candidateId!,
        sourceImageHash: sourceImageHash!,
        shotMapping: normalizedMapping,
        immutableSummary: {
          directionId: snapshot?.selectedDirectionId ?? (handoff.directionId as StudioHandoffContext['directionId']),
          ...(nonEmptyString(storyboardPackage?.locksHash, storyboardPackage?.locks_hash, rootPackage?.locksHash, rootPackage?.locks_hash) ? { locksHash: nonEmptyString(storyboardPackage?.locksHash, storyboardPackage?.locks_hash, rootPackage?.locksHash, rootPackage?.locks_hash)! } : {}),
          ...(nonEmptyString(storyboardPackage?.preservationHash, storyboardPackage?.preservation_hash, rootPackage?.preservationHash, rootPackage?.preservation_hash) ? { preservationHash: nonEmptyString(storyboardPackage?.preservationHash, storyboardPackage?.preservation_hash, rootPackage?.preservationHash, rootPackage?.preservation_hash)! } : {}),
          ...(positiveNumber(storyboardPackage?.factsRevision, storyboardPackage?.facts_revision, rootPackage?.factsRevision, rootPackage?.facts_revision) ? { factsRevision: positiveNumber(storyboardPackage?.factsRevision, storyboardPackage?.facts_revision, rootPackage?.factsRevision, rootPackage?.facts_revision)! } : {}),
        },
      })
    : null
  const basePreflight = snapshot?.handoff ? prepareProductionBridge(snapshot.handoff, 'VIDEO_DIRECTOR_FIXED') : null
  return {
    schemaVersion: DIRECTOR_FIXED_OFFLINE_INPUT_SCHEMA_VERSION,
    mode: 'READ_ONLY',
    status: input ? 'READY' : 'BLOCKED',
    providerSubmissionAllowed: false,
    qualificationScope: PRODUCTION_BRIDGE_QUALIFICATION_SCOPE,
    input,
    creativeTaskId,
    packageId,
    packageRevision,
    shotId,
    candidateId,
    sourceImageHash,
    shotMapping: normalizedMapping,
    missingFields,
    preflight: basePreflight?.preflight ?? null,
  }
}

export function prepareProductionBridge(
  handoff: StudioHandoffContext | null,
  purpose: ProductionBridgePurpose = 'VIDEO_DIRECTOR_FIXED',
): ProductionBridgePreparation | null {
  if (!handoff) return null
  const { preflight, blockingReasons } = createPreflightResult({ ...preflightChecks })

  return {
    schemaVersion: PRODUCTION_BRIDGE_PREFLIGHT_SCHEMA_VERSION,
    source: 'director-studio',
    purpose,
    status: 'PREFLIGHT_REQUIRED',
    executionMode: 'OFFLINE_SYNTHETIC_ONLY',
    providerSubmissionAllowed: false,
    qualificationScope: PRODUCTION_BRIDGE_QUALIFICATION_SCOPE,
    ...(handoff.projectId ? { projectId: handoff.projectId } : {}),
    directionId: handoff.directionId,
    packageId: handoff.packageId,
    packageRevision: handoff.packageRevision,
    shotId: handoff.shotId,
    checks: { ...preflightChecks },
    blockingReasons,
    preflight,
    reality: mapCreativeIntelligenceSnapshotToReality(handoff.intelligenceSnapshot),
    nextSteps: [
      'SERVER_VALIDATED_PACKAGE_REQUIRED',
      'MATERIALIZED_SOURCE_MAPPING_REQUIRED',
      'HUMAN_PROVIDER_AUTHORIZATION_REQUIRED',
    ],
  }
}

export function isProductionBridgePreparation(
  value: unknown,
): value is ProductionBridgePreparation {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Partial<ProductionBridgePreparation>
  return candidate.source === 'director-studio'
    && candidate.schemaVersion === PRODUCTION_BRIDGE_PREFLIGHT_SCHEMA_VERSION
    && candidate.providerSubmissionAllowed === false
    && candidate.qualificationScope === PRODUCTION_BRIDGE_QUALIFICATION_SCOPE
    && candidate.executionMode === 'OFFLINE_SYNTHETIC_ONLY'
    && (candidate.status === 'PLANNING_ONLY' || candidate.status === 'PREFLIGHT_REQUIRED')
    && typeof candidate.packageId === 'string'
    && typeof candidate.packageRevision === 'number'
    && typeof candidate.shotId === 'string'
    && Array.isArray(candidate.blockingReasons)
    && typeof candidate.preflight === 'object'
    && candidate.preflight !== null
    && candidate.preflight.schemaVersion === PRODUCTION_BRIDGE_PREFLIGHT_SCHEMA_VERSION
    && candidate.preflight.mode === 'READ_ONLY'
    && candidate.preflight.providerSubmissionAllowed === false
    && typeof candidate.reality === 'object'
    && candidate.reality !== null
}
