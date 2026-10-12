export const REALITY_ENGINE_EXECUTION_MODE = 'OFFLINE_SYNTHETIC_ONLY' as const

export type RealityEngineExecutionMode = typeof REALITY_ENGINE_EXECUTION_MODE

export type RealityDNAOrigin =
  | 'OBSERVED_REFERENCE'
  | 'USER_CONFIRMED'
  | 'SYNTHETIC_REFERENCE'
  | 'UNRESOLVED'

export type RealityEvidenceSource = 'asset' | 'project' | 'memory' | 'synthetic'

export interface RealityEvidence {
  sourceId: string
  source: RealityEvidenceSource
  statement: string
  confidence?: number
}

export interface RealityDNAHeader {
  id: string
  revision: number
  origin: RealityDNAOrigin
  confidence: number
  evidence: RealityEvidence[]
  constraints: string[]
}

export interface CharacterDNA {
  id: string
  revision: number
  origin: RealityDNAOrigin
  confidence: number
  identity: {
    role?: string
    ageRange?: string
    presentation?: string
    expression?: string
  }
  continuity: {
    appearance: string[]
    wardrobe: string[]
    behavior: string[]
  }
  evidence: RealityEvidence[]
  constraints: string[]
}

export interface SceneDNA {
  id: string
  revision: number
  origin: RealityDNAOrigin
  confidence: number
  environment: {
    location?: string
    timeOfDay?: string
    weather?: string
    season?: string
  }
  lighting: {
    source?: string
    direction?: string
    quality?: string
    contrast?: string
  }
  spatialAnchors: string[]
  continuity: string[]
  evidence: RealityEvidence[]
  constraints: string[]
}

export interface CameraDNA {
  id: string
  revision: number
  origin: RealityDNAOrigin
  confidence: number
  framing: {
    shot?: string
    aspectRatio?: string
    subjectPlacement?: string
    headroom?: string
  }
  lens: {
    focalLength?: string
    depthOfField?: string
    distortion?: string
  }
  motion: {
    movement?: string
    speed?: string
    stabilization?: string
  }
  composition: string[]
  evidence: RealityEvidence[]
  constraints: string[]
}

export interface StyleDNA {
  id: string
  revision: number
  origin: RealityDNAOrigin
  confidence: number
  visualTreatment: {
    palette?: string
    contrast?: string
    texture?: string
    grade?: string
  }
  references: string[]
  continuity: string[]
  evidence: RealityEvidence[]
  constraints: string[]
}

export interface RealitySnapshot {
  id: string
  revision: number
  mode: RealityEngineExecutionMode
  status: 'PREFLIGHT_REQUIRED'
  source: 'creative-project'
  capturedAt?: string
  referenceStrength?: number
  characterDNA?: CharacterDNA
  sceneDNA?: SceneDNA
  cameraDNA?: CameraDNA
  styleDNA?: StyleDNA
}

export interface RealitySnapshotMapping {
  source: 'creative-intelligence-snapshot'
  mode: RealityEngineExecutionMode
  status: 'PREFLIGHT_REQUIRED'
  snapshotId: string | null
  snapshotRevision: number | null
  dna: {
    characterDNAId: string | null
    sceneDNAId: string | null
    cameraDNAId: string | null
    styleDNAId: string | null
  }
}

export function isRealitySnapshot(value: unknown): value is RealitySnapshot {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Partial<RealitySnapshot>
  return candidate.source === 'creative-project'
    && candidate.mode === REALITY_ENGINE_EXECUTION_MODE
    && candidate.status === 'PREFLIGHT_REQUIRED'
    && typeof candidate.id === 'string'
    && typeof candidate.revision === 'number'
}
