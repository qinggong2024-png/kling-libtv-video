import type {
  CreativeProjectResearchContext,
  ReferenceVideoMetadata,
  ResearchAdapter,
  ResearchEvidence,
  VideoBlueprint,
  MotionDna,
  VideoReplicationResearch,
} from './types'

const OFFLINE_RETRIEVED_AT = '1970-01-01T00:00:00.000Z'

function assertNonEmpty(value: string, field: string): void {
  if (!value.trim()) throw new Error(`${field} must not be blank`)
}

function validateReferenceMetadata(metadata: ReferenceVideoMetadata): void {
  assertNonEmpty(metadata.id, 'referenceVideo.id')
  assertNonEmpty(metadata.title, 'referenceVideo.title')
  assertNonEmpty(metadata.rightsNote, 'referenceVideo.rightsNote')
  if (metadata.sourceUrl && !/^https?:\/\//.test(metadata.sourceUrl)) {
    throw new Error('referenceVideo.sourceUrl must use http or https')
  }
  if (metadata.durationSeconds !== undefined && metadata.durationSeconds <= 0) {
    throw new Error('referenceVideo.durationSeconds must be positive')
  }
  if (metadata.evidenceIds.length === 0) {
    throw new Error('referenceVideo.evidenceIds must contain at least one evidence id')
  }
}

function validateDna(motionDna: MotionDna): void {
  assertNonEmpty(motionDna.id, 'motionDna.id')
  if (motionDna.segments.length === 0) throw new Error('motionDna.segments must not be empty')
  for (const segment of motionDna.segments) {
    if (segment.endSeconds <= segment.startSeconds) {
      throw new Error(`motionDna segment ${segment.id} must have a positive duration`)
    }
  }
}

function validateBlueprint(videoBlueprint: VideoBlueprint): void {
  assertNonEmpty(videoBlueprint.id, 'videoBlueprint.id')
  if (videoBlueprint.durationSeconds <= 0) {
    throw new Error('videoBlueprint.durationSeconds must be positive')
  }
  if (videoBlueprint.shots.length === 0) throw new Error('videoBlueprint.shots must not be empty')
  const orders = videoBlueprint.shots.map((shot) => shot.order)
  if (orders.some((order, index) => order !== index + 1)) {
    throw new Error('videoBlueprint.shots must have contiguous order starting at 1')
  }
}

export function createReferenceVideoMetadata(
  input: Omit<ReferenceVideoMetadata, 'retrievedAt'> & { retrievedAt?: string },
): ReferenceVideoMetadata {
  const metadata: ReferenceVideoMetadata = {
    ...input,
    retrievedAt: input.retrievedAt ?? OFFLINE_RETRIEVED_AT,
    evidenceIds: [...input.evidenceIds],
  }
  validateReferenceMetadata(metadata)
  return metadata
}

export function createVideoReplicationResearch(input: {
  project: CreativeProjectResearchContext
  referenceVideo: ReferenceVideoMetadata
  motionDna: MotionDna
  videoBlueprint: VideoBlueprint
  evidence?: ResearchEvidence[]
}): VideoReplicationResearch {
  validateReferenceMetadata(input.referenceVideo)
  validateDna(input.motionDna)
  validateBlueprint(input.videoBlueprint)

  return {
    schemaVersion: 'video-replication-research.v1',
    status: 'PREFLIGHT_REQUIRED',
    qualificationScope: 'OFFLINE_SYNTHETIC_ONLY',
    project: input.project,
    referenceVideo: input.referenceVideo,
    motionDna: input.motionDna,
    videoBlueprint: input.videoBlueprint,
    evidence: [...(input.evidence ?? [])],
    providerSubmissionAllowed: false,
    productionBridgeStatus: 'PREFLIGHT_REQUIRED',
  }
}

export function createOfflineSyntheticResearchAdapter(): ResearchAdapter {
  return {
    createReferenceMetadata: createReferenceVideoMetadata,
    createResearch: createVideoReplicationResearch,
  }
}

export function isVideoReplicationResearch(value: unknown): value is VideoReplicationResearch {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Partial<VideoReplicationResearch>
  return candidate.schemaVersion === 'video-replication-research.v1'
    && candidate.qualificationScope === 'OFFLINE_SYNTHETIC_ONLY'
    && candidate.providerSubmissionAllowed === false
    && candidate.productionBridgeStatus === 'PREFLIGHT_REQUIRED'
    && candidate.status === 'PREFLIGHT_REQUIRED'
}
