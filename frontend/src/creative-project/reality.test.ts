import { describe, expect, it } from 'vitest'
import { createCreativeProject } from './project'
import {
  attachRealitySnapshotToProject,
  mapCreativeIntelligenceSnapshotToReality,
  mapRealitySnapshotToCreativeIntelligence,
  selectRealitySnapshot,
} from './realityAdapters'
import { isRealitySnapshot, type RealitySnapshot } from './reality'

const realitySnapshot: RealitySnapshot = {
  id: 'reality-1',
  revision: 2,
  mode: 'OFFLINE_SYNTHETIC_ONLY',
  status: 'PREFLIGHT_REQUIRED',
  source: 'creative-project',
  referenceStrength: 0.84,
  characterDNA: {
    id: 'character-1',
    revision: 1,
    origin: 'USER_CONFIRMED',
    confidence: 0.9,
    identity: { role: 'hero', presentation: 'adult' },
    continuity: {
      appearance: ['natural expression'],
      wardrobe: ['preserve garment silhouette'],
      behavior: ['calm movement'],
    },
    evidence: [{ sourceId: 'asset-1', source: 'asset', statement: 'front reference' }],
    constraints: ['do not change garment identity'],
  },
  sceneDNA: {
    id: 'scene-1',
    revision: 1,
    origin: 'SYNTHETIC_REFERENCE',
    confidence: 0.7,
    environment: { location: 'city corner', timeOfDay: 'day' },
    lighting: { source: 'overcast daylight', quality: 'soft' },
    spatialAnchors: ['sidewalk', 'shopfront'],
    continuity: ['keep subject on the same side of frame'],
    evidence: [{ sourceId: 'direction-A', source: 'project', statement: 'selected direction' }],
    constraints: ['no new branded signage'],
  },
  cameraDNA: {
    id: 'camera-1',
    revision: 1,
    origin: 'SYNTHETIC_REFERENCE',
    confidence: 0.65,
    framing: { shot: 'medium close-up', aspectRatio: '9:16' },
    lens: { focalLength: '50mm', depthOfField: 'moderate' },
    motion: { movement: 'follow', speed: 'slow' },
    composition: ['subject centered after turn'],
    evidence: [{ sourceId: 'package-1', source: 'project', statement: 'package camera note' }],
    constraints: ['preserve headroom'],
  },
  styleDNA: {
    id: 'style-1',
    revision: 1,
    origin: 'OBSERVED_REFERENCE',
    confidence: 0.8,
    visualTreatment: { palette: 'neutral', contrast: 'soft', texture: 'natural' },
    references: ['direction-A'],
    continuity: ['retain realistic fabric texture'],
    evidence: [{ sourceId: 'asset-1', source: 'asset', statement: 'material texture' }],
    constraints: ['no stylized illustration treatment'],
  },
}

describe('Reality Engine preparation adapters', () => {
  it('maps a Reality Snapshot into the existing CreativeIntelligenceSnapshot extension point', () => {
    const intelligence = mapRealitySnapshotToCreativeIntelligence(realitySnapshot, {
      videoReference: { videoDNAId: 'video-1' },
    })

    expect(intelligence.realityEngineMode).toBe('OFFLINE_SYNTHETIC_ONLY')
    expect(intelligence.realityReference?.realityDNAId).toBe('reality-1')
    expect(intelligence.characterDNA?.id).toBe('character-1')
    expect(intelligence.videoReference?.videoDNAId).toBe('video-1')
    expect(intelligence.realitySnapshot).toEqual(realitySnapshot)
  })

  it('attaches only intelligence metadata to a CreativeProject', () => {
    const project = attachRealitySnapshotToProject(
      createCreativeProject({ id: 'project-1', revision: 4 }),
      realitySnapshot,
    )

    expect(project.revision).toBe(5)
    expect(selectRealitySnapshot(project)?.id).toBe('reality-1')
    expect('phase' in project).toBe(false)
    expect('task' in project).toBe(false)
  })

  it('maps stable DNA ids for the read-only Production Bridge', () => {
    const mapping = mapCreativeIntelligenceSnapshotToReality(
      mapRealitySnapshotToCreativeIntelligence(realitySnapshot),
    )

    expect(mapping).toEqual({
      source: 'creative-intelligence-snapshot',
      mode: 'OFFLINE_SYNTHETIC_ONLY',
      status: 'PREFLIGHT_REQUIRED',
      snapshotId: 'reality-1',
      snapshotRevision: 2,
      dna: {
        characterDNAId: 'character-1',
        sceneDNAId: 'scene-1',
        cameraDNAId: 'camera-1',
        styleDNAId: 'style-1',
      },
    })
  })

  it('recognizes only the offline preflight Reality Snapshot shape', () => {
    expect(isRealitySnapshot(realitySnapshot)).toBe(true)
    expect(isRealitySnapshot({ ...realitySnapshot, mode: 'LIVE' })).toBe(false)
    expect(isRealitySnapshot({ id: 'reality-1' })).toBe(false)
  })
})
