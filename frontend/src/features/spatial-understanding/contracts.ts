export const SPATIAL_SCHEMA_VERSION = 'spatial-dna.v1' as const
export const DEPTH_SCHEMA_VERSION = 'depth-reference.v1' as const
export const CAMERA_SCHEMA_VERSION = 'camera-relationship.v1' as const
export const MOTION_SCHEMA_VERSION = 'motion-reference-placeholder.v1' as const

export type SpatialExecutionMode = 'OFFLINE_SYNTHETIC_ONLY'
export type SpatialPreflightStatus = 'PREFLIGHT_REQUIRED'

export interface DepthReference {
  schemaVersion: typeof DEPTH_SCHEMA_VERSION
  entityId: string
  depthBand: 'FOREGROUND' | 'MIDGROUND' | 'BACKGROUND' | 'UNKNOWN'
  relativeOrder?: number
  confidence: number
  source: 'HUMAN_ANNOTATION' | 'SYNTHETIC_PLACEHOLDER' | 'UNSPECIFIED'
  notes?: string
}

export interface CameraRelationship {
  schemaVersion: typeof CAMERA_SCHEMA_VERSION
  cameraId: string
  subjectId: string
  relationship:
    | 'FRONTAL'
    | 'THREE_QUARTER'
    | 'PROFILE'
    | 'OVER_SHOULDER'
    | 'TOP_DOWN'
    | 'LOW_ANGLE'
    | 'UNKNOWN'
  framing: 'WIDE' | 'MEDIUM_WIDE' | 'MEDIUM' | 'MEDIUM_CLOSE' | 'CLOSE' | 'UNKNOWN'
  screenSide?: 'LEFT' | 'CENTER' | 'RIGHT' | 'UNKNOWN'
  notes?: string
}

export interface MotionReferencePlaceholder {
  schemaVersion: typeof MOTION_SCHEMA_VERSION
  mode: SpatialExecutionMode
  preflightStatus: SpatialPreflightStatus
  providerSubmissionAllowed: false
  placeholderId: string
  motionClass:
    | 'STILLNESS'
    | 'WEIGHT_SHIFT'
    | 'GESTURE'
    | 'WALK_CYCLE'
    | 'CAMERA_DRIFT'
    | 'UNKNOWN'
  source: 'HUMAN_INTENT' | 'SYNTHETIC_PLACEHOLDER' | 'UNSPECIFIED'
  description?: string
  constraints?: string[]
}

export interface SpatialDNA {
  schemaVersion: typeof SPATIAL_SCHEMA_VERSION
  mode: SpatialExecutionMode
  preflightStatus: SpatialPreflightStatus
  providerSubmissionAllowed: false
  referenceId: string
  coordinateSystem: 'IMAGE_NORMALIZED_2D' | 'SCREEN_SPACE_2D'
  depthReferences: DepthReference[]
  cameraRelationships: CameraRelationship[]
  occlusionRelations: Array<{
    frontEntityId: string
    backEntityId: string
    relation: 'FRONT_OCCLUDES_BACK'
  }>
  evidence?: string[]
}

export interface SpatialReferenceDraft {
  referenceId: string
  coordinateSystem?: SpatialDNA['coordinateSystem']
  depthReferences?: Array<Omit<DepthReference, 'schemaVersion'>>
  cameraRelationships?: Array<Omit<CameraRelationship, 'schemaVersion'>>
  occlusionRelations?: SpatialDNA['occlusionRelations']
  evidence?: string[]
}
