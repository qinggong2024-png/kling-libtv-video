export type {
  CameraMovement,
  CameraPlan,
  CreativeProjectResearchContext,
  MotionDna,
  MotionDnaEvidence,
  MotionDnaSegment,
  ReferenceVideoMetadata,
  ReferenceVideoSource,
  ResearchAdapter,
  ResearchEvidence,
  ResearchStatus,
  VideoBlueprint,
  VideoBlueprintShot,
  VideoBlueprintSource,
  VideoReplicationResearch,
} from './types'

export {
  createOfflineSyntheticResearchAdapter,
  createReferenceVideoMetadata,
  createVideoReplicationResearch,
  isVideoReplicationResearch,
} from './adapters'
