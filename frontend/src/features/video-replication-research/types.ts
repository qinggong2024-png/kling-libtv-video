import type { CreativeIntelligenceSnapshot, CreativeProject } from '../../creative-project/types'

export type ResearchStatus = 'DRAFT' | 'PREFLIGHT_REQUIRED'
export type ReferenceVideoSource = 'USER_PROVIDED' | 'PUBLIC_REFERENCE' | 'INTERNAL_LIBRARY'
export type VideoBlueprintSource = 'USER_PROVIDED' | 'PLANNING_DERIVED'
export type CameraMovement =
  | 'STATIC'
  | 'PAN'
  | 'TILT'
  | 'DOLLY'
  | 'TRACK'
  | 'HANDHELD'
  | 'ZOOM'
  | 'ROTATION'

export interface ResearchEvidence {
  id: string
  kind: 'OBSERVATION' | 'USER_NOTE' | 'SOURCE_METADATA'
  label: string
  note: string
  sourceRef?: string
}

export interface ReferenceVideoMetadata {
  id: string
  source: ReferenceVideoSource
  title: string
  sourceUrl?: string
  creator?: string
  platform?: string
  publishedAt?: string
  retrievedAt: string
  durationSeconds?: number
  width?: number
  height?: number
  frameRate?: number
  hasAudio?: boolean
  language?: string
  rightsNote: string
  checksum?: string
  evidenceIds: string[]
}

export interface MotionDnaEvidence {
  evidenceId: string
  confidence: 'LOW' | 'MEDIUM' | 'HIGH'
  rationale: string
}

export interface MotionDnaSegment {
  id: string
  startSeconds: number
  endSeconds: number
  subjectAction: string
  subjectState: string
  cameraMovement: CameraMovement
  cameraIntensity: 'LOW' | 'MEDIUM' | 'HIGH'
  framing: string
  pacing: 'SLOW' | 'MODERATE' | 'FAST'
  productFocus: string
  evidence: MotionDnaEvidence[]
}

export interface MotionDna {
  id: string
  version: string
  summary: string
  segments: MotionDnaSegment[]
  continuityRules: string[]
  forbiddenInferences: string[]
  evidenceIds: string[]
}

export interface CameraPlan {
  movement: CameraMovement
  framing: string
  lensIntent: string
  stability: 'LOCKED' | 'CONTROLLED_HANDHELD' | 'HANDHELD'
  durationSeconds?: number
}

export interface VideoBlueprintShot {
  id: string
  order: number
  startSeconds: number
  endSeconds: number
  purpose: string
  subjectAction: string
  camera: CameraPlan
  productDisplay: string
  continuityConstraints: string[]
  sourceSegmentIds: string[]
}

export interface VideoBlueprint {
  id: string
  version: string
  title: string
  source: VideoBlueprintSource
  durationSeconds: number
  aspectRatio: string
  audioIntent: 'NONE' | 'REFERENCE_ONLY' | 'UNSPECIFIED'
  shots: VideoBlueprintShot[]
  invariants: string[]
  excludedElements: string[]
}

export interface CreativeProjectResearchContext {
  projectId: CreativeProject['id']
  projectRevision?: CreativeProject['revision']
  intelligenceSnapshot?: CreativeIntelligenceSnapshot
}

export interface VideoReplicationResearch {
  schemaVersion: 'video-replication-research.v1'
  status: ResearchStatus
  qualificationScope: 'OFFLINE_SYNTHETIC_ONLY'
  project: CreativeProjectResearchContext
  referenceVideo: ReferenceVideoMetadata
  motionDna: MotionDna
  videoBlueprint: VideoBlueprint
  evidence: ResearchEvidence[]
  providerSubmissionAllowed: false
  productionBridgeStatus: 'PREFLIGHT_REQUIRED'
}

export interface ResearchAdapter {
  createReferenceMetadata(
    input: Omit<ReferenceVideoMetadata, 'retrievedAt'> & { retrievedAt?: string },
  ): ReferenceVideoMetadata
  createResearch(input: {
    project: CreativeProjectResearchContext
    referenceVideo: ReferenceVideoMetadata
    motionDna: MotionDna
    videoBlueprint: VideoBlueprint
    evidence?: ResearchEvidence[]
  }): VideoReplicationResearch
}
