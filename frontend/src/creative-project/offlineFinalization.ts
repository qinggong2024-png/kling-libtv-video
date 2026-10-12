import type { CreativeMemoryEntry } from './memory'
import type { CreativeProject } from './types'
import {
  prepareProductionBridge,
} from '../features/director-studio/productionBridge'
import { selectDirectorHandoffFromProject } from '../features/director-studio/directorHandoff'

export const OFFLINE_FINALIZATION_MODE = 'OFFLINE_SYNTHETIC_ONLY' as const
export const OFFLINE_FINALIZATION_PREFLIGHT = 'PREFLIGHT_REQUIRED' as const

export interface OfflineMediaEvidence {
  id: string
  synthetic: true
  providerSubmissionAllowed: false
  qualificationScope: typeof OFFLINE_FINALIZATION_MODE
}

export interface OfflineQualityEvidence {
  subjectId: string
  recommendation: 'PASS' | 'WARNING' | 'QUALITY_REVIEW' | 'UNRESOLVED'
  evidenceRefs: string[]
  mode: typeof OFFLINE_FINALIZATION_MODE
}

export interface OfflineFinalizationInput {
  project: CreativeProject
  imageResult: OfflineMediaEvidence
  videoResult: OfflineMediaEvidence
  qualityReview: OfflineQualityEvidence
  memory: readonly CreativeMemoryEntry[]
}

export type OfflineFinalizationStage =
  | 'product-input'
  | 'director-studio'
  | 'production-package'
  | 'production-bridge-preflight'
  | 'image-studio'
  | 'video-studio'
  | 'quality-review'
  | 'creative-memory'

export interface OfflineFinalizationResult {
  mode: typeof OFFLINE_FINALIZATION_MODE
  preflightStatus: typeof OFFLINE_FINALIZATION_PREFLIGHT
  providerSubmissionAllowed: false
  completedStages: readonly OfflineFinalizationStage[]
  blockingReasons: readonly string[]
  directorPackageId: string | null
  bridgePurpose: 'IMAGE_FIRST_FRAME'
}

function hasProduct(project: CreativeProject): boolean {
  return project.assets.some((asset) => asset.kind === 'product')
}

function hasMemoryKind(
  entries: readonly CreativeMemoryEntry[],
  kind: CreativeMemoryEntry['kind'],
): boolean {
  return entries.some((entry) => entry.kind === kind)
}

function mediaEvidenceIsOffline(value: OfflineMediaEvidence): boolean {
  return value.synthetic === true
    && value.providerSubmissionAllowed === false
    && value.qualificationScope === OFFLINE_FINALIZATION_MODE
    && value.id.trim().length > 0
}

export function verifyOfflineCreativeOsFinalization(
  input: OfflineFinalizationInput,
): OfflineFinalizationResult {
  const completedStages: OfflineFinalizationStage[] = []
  const blockingReasons: string[] = []

  if (hasProduct(input.project)) completedStages.push('product-input')
  else blockingReasons.push('PRODUCT_INPUT_REQUIRED')

  const handoff = selectDirectorHandoffFromProject(input.project)
  if (handoff) completedStages.push('director-studio')
  else blockingReasons.push('DIRECTOR_HANDOFF_REQUIRED')

  if (handoff?.packageId && handoff.packageRevision > 0) {
    completedStages.push('production-package')
  } else {
    blockingReasons.push('PRODUCTION_PACKAGE_REQUIRED')
  }

  const bridge = handoff ? prepareProductionBridge(handoff, 'IMAGE_FIRST_FRAME') : null
  if (
    bridge
    && bridge.status === OFFLINE_FINALIZATION_PREFLIGHT
    && bridge.executionMode === OFFLINE_FINALIZATION_MODE
    && bridge.providerSubmissionAllowed === false
  ) {
    completedStages.push('production-bridge-preflight')
  } else {
    blockingReasons.push('PRODUCTION_BRIDGE_PREFLIGHT_REQUIRED')
  }

  if (mediaEvidenceIsOffline(input.imageResult)) completedStages.push('image-studio')
  else blockingReasons.push('OFFLINE_IMAGE_RESULT_REQUIRED')

  if (mediaEvidenceIsOffline(input.videoResult)) completedStages.push('video-studio')
  else blockingReasons.push('OFFLINE_VIDEO_RESULT_REQUIRED')

  if (
    input.qualityReview.mode === OFFLINE_FINALIZATION_MODE
    && input.qualityReview.subjectId === input.videoResult.id
    && input.qualityReview.evidenceRefs.length > 0
  ) {
    completedStages.push('quality-review')
  } else {
    blockingReasons.push('OFFLINE_QUALITY_REVIEW_REQUIRED')
  }

  const requiredMemoryKinds: CreativeMemoryEntry['kind'][] = [
    'direction-history',
    'candidate-selection',
    'production-package-revision',
    'bridge-decision',
  ]
  if (requiredMemoryKinds.every((kind) => hasMemoryKind(input.memory, kind))) {
    completedStages.push('creative-memory')
  } else {
    blockingReasons.push('CREATIVE_MEMORY_RECORDS_REQUIRED')
  }

  return {
    mode: OFFLINE_FINALIZATION_MODE,
    preflightStatus: OFFLINE_FINALIZATION_PREFLIGHT,
    providerSubmissionAllowed: false,
    completedStages,
    blockingReasons,
    directorPackageId: handoff?.packageId ?? null,
    bridgePurpose: 'IMAGE_FIRST_FRAME',
  }
}
