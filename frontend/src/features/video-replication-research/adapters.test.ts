import { describe, expect, it } from 'vitest'
import {
  createOfflineSyntheticResearchAdapter,
  createReferenceVideoMetadata,
  createVideoReplicationResearch,
  isVideoReplicationResearch,
} from './index'
import type { MotionDna, VideoBlueprint } from './types'

const reference = createReferenceVideoMetadata({
  id: 'ref-1',
  source: 'PUBLIC_REFERENCE',
  title: 'Reference sample',
  sourceUrl: 'https://example.com/video',
  retrievedAt: '2026-10-12T00:00:00.000Z',
  rightsNote: 'Research reference only; no production reuse.',
  evidenceIds: ['evidence-1'],
})

const motionDna: MotionDna = {
  id: 'motion-1',
  version: '1.0',
  summary: 'Controlled walk-in with a short three-quarter turn.',
  segments: [{
    id: 'segment-1',
    startSeconds: 0,
    endSeconds: 3,
    subjectAction: 'walk in and settle',
    subjectState: 'standing',
    cameraMovement: 'TRACK',
    cameraIntensity: 'LOW',
    framing: 'full body',
    pacing: 'MODERATE',
    productFocus: 'silhouette',
    evidence: [{ evidenceId: 'evidence-1', confidence: 'MEDIUM', rationale: 'Visible in source sample.' }],
  }],
  continuityRules: ['Preserve subject identity and garment construction.'],
  forbiddenInferences: ['Do not infer unseen back print details.'],
  evidenceIds: ['evidence-1'],
}

const videoBlueprint: VideoBlueprint = {
  id: 'blueprint-1',
  version: '1.0',
  title: 'Reference motion study',
  source: 'PLANNING_DERIVED',
  durationSeconds: 3,
  aspectRatio: '9:16',
  audioIntent: 'REFERENCE_ONLY',
  shots: [{
    id: 'shot-1',
    order: 1,
    startSeconds: 0,
    endSeconds: 3,
    purpose: 'Establish silhouette and controlled motion.',
    subjectAction: 'walk in and settle',
    camera: {
      movement: 'TRACK',
      framing: 'full body',
      lensIntent: 'observational',
      stability: 'CONTROLLED_HANDHELD',
      durationSeconds: 3,
    },
    productDisplay: 'Keep garment unobstructed.',
    continuityConstraints: ['Do not add unseen accessories.'],
    sourceSegmentIds: ['segment-1'],
  }],
  invariants: ['Keep source subject and garment facts unchanged.'],
  excludedElements: ['provider parameters', 'billing instructions'],
}

describe('video replication research adapter', () => {
  it('creates an offline-only research package without provider fields', () => {
    const research = createVideoReplicationResearch({
      project: { projectId: 'project-1', projectRevision: 2 },
      referenceVideo: reference,
      motionDna,
      videoBlueprint,
      evidence: [{
        id: 'evidence-1',
        kind: 'OBSERVATION',
        label: 'Source observation',
        note: 'The subject settles before the end of the shot.',
      }],
    })

    expect(research.status).toBe('PREFLIGHT_REQUIRED')
    expect(research.qualificationScope).toBe('OFFLINE_SYNTHETIC_ONLY')
    expect(research.providerSubmissionAllowed).toBe(false)
    expect(isVideoReplicationResearch(research)).toBe(true)
  })

  it('uses a deterministic retrieval fallback in the offline adapter', () => {
    const adapter = createOfflineSyntheticResearchAdapter()
    expect(adapter.createReferenceMetadata({
      ...reference,
      retrievedAt: undefined,
    }).retrievedAt).toBe('1970-01-01T00:00:00.000Z')
  })

  it('rejects invalid reference metadata and non-contiguous shots', () => {
    expect(() => createReferenceVideoMetadata({
      ...reference,
      sourceUrl: 'file:///secret/video.mp4',
    })).toThrow('http or https')

    expect(() => createVideoReplicationResearch({
      project: { projectId: 'project-1' },
      referenceVideo: reference,
      motionDna,
      videoBlueprint: {
        ...videoBlueprint,
        shots: [{ ...videoBlueprint.shots[0], order: 2 }],
      },
    })).toThrow('contiguous order')
  })
})
