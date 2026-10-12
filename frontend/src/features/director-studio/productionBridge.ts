import type { StudioHandoffContext } from './contracts'
import { mapCreativeIntelligenceSnapshotToReality } from '../../creative-project/realityAdapters'
import type { RealityEngineExecutionMode, RealitySnapshotMapping } from '../../creative-project/reality'

export type ProductionBridgePurpose = 'IMAGE_FIRST_FRAME' | 'VIDEO_DIRECTOR_FIXED'
export type ProductionBridgePreparationStatus = 'PLANNING_ONLY' | 'PREFLIGHT_REQUIRED'
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

export interface ProductionBridgePreparation {
  source: 'director-studio'
  purpose: ProductionBridgePurpose
  status: ProductionBridgePreparationStatus
  executionMode: ProductionBridgeExecutionMode
  providerSubmissionAllowed: false
  projectId?: string
  directionId: StudioHandoffContext['directionId']
  packageId: string
  packageRevision: number
  shotId: StudioHandoffContext['shotId']
  checks: ProductionBridgeChecks
  reality: RealitySnapshotMapping
  blockingReasons: string[]
  nextSteps: [
    'SERVER_VALIDATED_PACKAGE_REQUIRED',
    'MATERIALIZED_SOURCE_MAPPING_REQUIRED',
    'HUMAN_PROVIDER_AUTHORIZATION_REQUIRED',
  ]
}

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

export function prepareProductionBridge(
  handoff: StudioHandoffContext | null,
  purpose: ProductionBridgePurpose = 'VIDEO_DIRECTOR_FIXED',
): ProductionBridgePreparation | null {
  if (!handoff) return null

  return {
    source: 'director-studio',
    purpose,
    status: 'PREFLIGHT_REQUIRED',
    executionMode: 'OFFLINE_SYNTHETIC_ONLY',
    providerSubmissionAllowed: false,
    ...(handoff.projectId ? { projectId: handoff.projectId } : {}),
    directionId: handoff.directionId,
    packageId: handoff.packageId,
    packageRevision: handoff.packageRevision,
    shotId: handoff.shotId,
    checks: { ...preflightChecks },
    reality: mapCreativeIntelligenceSnapshotToReality(handoff.intelligenceSnapshot),
    blockingReasons: [
      '当前 handoff 仍是前端只读上下文',
      '需要服务端重新校验 owner、package revision、lock hash、source hash 和 execution state',
      '需要服务端提供 materialized source mappings、license、budget 和 authorization evidence',
      '当前模式禁止 Provider submission',
    ],
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
    && candidate.providerSubmissionAllowed === false
    && candidate.executionMode === 'OFFLINE_SYNTHETIC_ONLY'
    && (candidate.status === 'PLANNING_ONLY' || candidate.status === 'PREFLIGHT_REQUIRED')
    && typeof candidate.packageId === 'string'
    && typeof candidate.packageRevision === 'number'
    && typeof candidate.shotId === 'string'
    && typeof candidate.reality === 'object'
    && candidate.reality !== null
}
