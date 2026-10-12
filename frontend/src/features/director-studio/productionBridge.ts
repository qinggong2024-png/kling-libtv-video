import type { StudioHandoffContext } from './contracts'
import { mapCreativeIntelligenceSnapshotToReality } from '../../creative-project/realityAdapters'
import type { RealityEngineExecutionMode, RealitySnapshotMapping } from '../../creative-project/reality'

export const PRODUCTION_BRIDGE_PREFLIGHT_SCHEMA_VERSION = 'production-bridge-preflight.v1' as const
export const PRODUCTION_BRIDGE_QUALIFICATION_SCOPE = 'OFFLINE_SYNTHETIC_ONLY' as const

export type ProductionBridgePurpose = 'IMAGE_FIRST_FRAME' | 'VIDEO_DIRECTOR_FIXED'
export type ProductionBridgePreparationStatus = 'PLANNING_ONLY' | 'PREFLIGHT_REQUIRED'
export type ProductionBridgeExecutionMode = RealityEngineExecutionMode
export type ProductionBridgeCheckStatus = 'UNVERIFIED' | 'PASS' | 'BLOCKED'
export type ProductionBridgeReadinessState = 'NOT_READY' | 'READY_FOR_HUMAN_CHECKPOINT'
export type ProductionBridgeApprovalStatus = 'REQUIRED' | 'ACCEPTED' | 'REJECTED'

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
  reality: RealitySnapshotMapping
  blockingReasons: ProductionBridgeBlockingReason[]
  preflight: ProductionBridgePreflightResult
  nextSteps: [
    'SERVER_VALIDATED_PACKAGE_REQUIRED',
    'MATERIALIZED_SOURCE_MAPPING_REQUIRED',
    'HUMAN_PROVIDER_AUTHORIZATION_REQUIRED',
  ]
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
    reality: mapCreativeIntelligenceSnapshotToReality(handoff.intelligenceSnapshot),
    blockingReasons,
    preflight,
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
    && candidate.executionMode === 'OFFLINE_SYNTHETIC_ONLY'
    && candidate.qualificationScope === PRODUCTION_BRIDGE_QUALIFICATION_SCOPE
    && (candidate.status === 'PLANNING_ONLY' || candidate.status === 'PREFLIGHT_REQUIRED')
    && typeof candidate.packageId === 'string'
    && typeof candidate.packageRevision === 'number'
    && typeof candidate.shotId === 'string'
    && typeof candidate.reality === 'object'
    && candidate.reality !== null
    && Array.isArray(candidate.blockingReasons)
    && typeof candidate.preflight === 'object'
    && candidate.preflight !== null
    && candidate.preflight.schemaVersion === PRODUCTION_BRIDGE_PREFLIGHT_SCHEMA_VERSION
    && candidate.preflight.mode === 'READ_ONLY'
    && candidate.preflight.providerSubmissionAllowed === false
}
