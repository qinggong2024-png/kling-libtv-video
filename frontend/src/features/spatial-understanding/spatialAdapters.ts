import {
  CAMERA_SCHEMA_VERSION,
  DEPTH_SCHEMA_VERSION,
  MOTION_SCHEMA_VERSION,
  SPATIAL_SCHEMA_VERSION,
  type MotionReferencePlaceholder,
  type SpatialDNA,
  type SpatialReferenceDraft,
} from './contracts'

const OFFLINE_MODE = 'OFFLINE_SYNTHETIC_ONLY' as const
const PREFLIGHT = 'PREFLIGHT_REQUIRED' as const

export function toSpatialDNA(draft: SpatialReferenceDraft): SpatialDNA {
  return {
    schemaVersion: SPATIAL_SCHEMA_VERSION,
    mode: OFFLINE_MODE,
    preflightStatus: PREFLIGHT,
    providerSubmissionAllowed: false,
    referenceId: draft.referenceId.trim(),
    coordinateSystem: draft.coordinateSystem ?? 'IMAGE_NORMALIZED_2D',
    depthReferences: (draft.depthReferences ?? []).map((reference) => ({
      ...reference,
      schemaVersion: DEPTH_SCHEMA_VERSION,
    })),
    cameraRelationships: (draft.cameraRelationships ?? []).map((relationship) => ({
      ...relationship,
      schemaVersion: CAMERA_SCHEMA_VERSION,
    })),
    occlusionRelations: [...(draft.occlusionRelations ?? [])],
    ...(draft.evidence?.length ? { evidence: [...draft.evidence] } : {}),
  }
}

export function createMotionReferencePlaceholder(
  placeholderId: string,
  motionClass: MotionReferencePlaceholder['motionClass'] = 'UNKNOWN',
  description?: string,
): MotionReferencePlaceholder {
  return {
    schemaVersion: MOTION_SCHEMA_VERSION,
    mode: OFFLINE_MODE,
    preflightStatus: PREFLIGHT,
    providerSubmissionAllowed: false,
    placeholderId: placeholderId.trim(),
    motionClass,
    source: 'SYNTHETIC_PLACEHOLDER',
    ...(description ? { description: description.trim() } : {}),
  }
}

export function isOfflineSpatialContract(value: unknown): value is {
  mode: typeof OFFLINE_MODE
  preflightStatus: typeof PREFLIGHT
  providerSubmissionAllowed: false
} {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Record<string, unknown>
  return candidate.mode === OFFLINE_MODE
    && candidate.preflightStatus === PREFLIGHT
    && candidate.providerSubmissionAllowed === false
}
