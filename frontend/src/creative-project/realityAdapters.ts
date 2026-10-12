import type { CreativeIntelligenceSnapshot, CreativeProject } from './types'
import {
  REALITY_ENGINE_EXECUTION_MODE,
  type RealitySnapshot,
  type RealitySnapshotMapping,
} from './reality'

function dnaId(value: { id?: string } | undefined): string | null {
  return value?.id ?? null
}

export function mapCreativeIntelligenceSnapshotToReality(
  snapshot?: CreativeIntelligenceSnapshot,
): RealitySnapshotMapping {
  const realitySnapshot = snapshot?.realitySnapshot
  return {
    source: 'creative-intelligence-snapshot',
    mode: snapshot?.realityEngineMode ?? realitySnapshot?.mode ?? REALITY_ENGINE_EXECUTION_MODE,
    status: 'PREFLIGHT_REQUIRED',
    snapshotId: realitySnapshot?.id ?? snapshot?.realityReference?.realityDNAId ?? null,
    snapshotRevision: realitySnapshot?.revision ?? null,
    dna: {
      characterDNAId: dnaId(snapshot?.characterDNA ?? realitySnapshot?.characterDNA),
      sceneDNAId: dnaId(snapshot?.sceneDNA ?? realitySnapshot?.sceneDNA),
      cameraDNAId: dnaId(snapshot?.cameraDNA ?? realitySnapshot?.cameraDNA),
      styleDNAId: dnaId(snapshot?.styleDNA ?? realitySnapshot?.styleDNA),
    },
  }
}

export function mapRealitySnapshotToCreativeIntelligence(
  realitySnapshot: RealitySnapshot,
  current?: CreativeIntelligenceSnapshot,
): CreativeIntelligenceSnapshot {
  return {
    ...current,
    realityEngineMode: realitySnapshot.mode,
    realityReference: {
      ...current?.realityReference,
      realityDNAId: realitySnapshot.id,
    },
    ...(realitySnapshot.characterDNA ? { characterDNA: realitySnapshot.characterDNA } : {}),
    ...(realitySnapshot.sceneDNA ? { sceneDNA: realitySnapshot.sceneDNA } : {}),
    ...(realitySnapshot.cameraDNA ? { cameraDNA: realitySnapshot.cameraDNA } : {}),
    ...(realitySnapshot.styleDNA ? { styleDNA: realitySnapshot.styleDNA } : {}),
    realitySnapshot,
    ...(realitySnapshot.referenceStrength === undefined
      ? {}
      : { referenceStrength: realitySnapshot.referenceStrength }),
  }
}

export function attachRealitySnapshotToProject(
  project: CreativeProject,
  realitySnapshot: RealitySnapshot,
): CreativeProject {
  return {
    ...project,
    revision: (project.revision ?? 0) + 1,
    intelligenceSnapshot: mapRealitySnapshotToCreativeIntelligence(
      realitySnapshot,
      project.intelligenceSnapshot,
    ),
  }
}

export function selectRealitySnapshot(project: CreativeProject): RealitySnapshot | null {
  return project.intelligenceSnapshot?.realitySnapshot ?? null
}
