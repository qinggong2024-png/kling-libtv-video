import type { DirectorCandidate, DirectorTaskResponse } from './directorApi'
import type { DirectorDraft } from './directorModel'
import type { DirectorPlanningSnapshot, ProductionPackage, StudioHandoffContext } from './contracts'
import type { CreativeIntelligenceSnapshot } from '../../creative-project/types'
import { toCreativeBrief, toDirectionCandidates, toProductionPackage } from './directorAdapters'

export function selectDirectorProductionPackage(
  workflow: DirectorTaskResponse | null,
): ProductionPackage | null {
  return workflow?.snapshot.package ? toProductionPackage(workflow.snapshot.package) : null
}

export function selectDirectorFirstFrameCandidates(
  workflow: DirectorTaskResponse | null,
): DirectorCandidate[] {
  return workflow?.snapshot.candidates.filter((candidate) => candidate.shot_id === 'FIRST_FRAME') ?? []
}

export function selectDirectorStoryboardPackage(
  workflow: DirectorTaskResponse | null,
) {
  return workflow?.snapshot.storyboard?.packages?.SHOT_01 ?? null
}

export function selectDirectorStoryboardCandidates(
  workflow: DirectorTaskResponse | null,
): DirectorCandidate[] {
  return workflow?.snapshot.storyboard?.candidates.filter(
    (candidate) => candidate.shot_id === 'SHOT_01',
  ) ?? []
}

export function selectDirectorStoryboardSelection(
  workflow: DirectorTaskResponse | null,
) {
  return workflow?.snapshot.storyboard?.selections?.SHOT_01 ?? null
}

export function selectDirectorStoryboardReview(
  workflow: DirectorTaskResponse | null,
) {
  return workflow?.snapshot.storyboard?.latest_reviews?.SHOT_01 ?? null
}

export function selectDirectorHandoff(
  workflow: DirectorTaskResponse | null,
  draft: DirectorDraft,
  projectId?: string,
  intelligenceSnapshot?: CreativeIntelligenceSnapshot,
): StudioHandoffContext | null {
  const packageRevision = selectDirectorProductionPackage(workflow)
  if (!packageRevision || packageRevision.shotId !== 'FIRST_FRAME' || !draft.selectedDirectionId || !draft.intake.productFrontFile) return null
  return {
    source: 'director-studio',
    ...(projectId ? { projectId } : {}),
    directionId: draft.selectedDirectionId,
    packageId: packageRevision.packageId,
    packageRevision: packageRevision.revision,
    shotId: packageRevision.shotId,
    ...(intelligenceSnapshot ? { intelligenceSnapshot } : {}),
    references: {
      productFront: true,
      selectedDirection: true,
      productionPackage: true,
    },
  }
}

export function selectDirectorPlanningSnapshot(
  workflow: DirectorTaskResponse | null,
  draft: DirectorDraft,
  projectId?: string,
  intelligenceSnapshot?: CreativeIntelligenceSnapshot,
): DirectorPlanningSnapshot {
  return {
    brief: toCreativeBrief(draft.intake),
    candidates: toDirectionCandidates(draft.directions),
    selectedDirectionId: draft.selectedDirectionId,
    productionPackage: selectDirectorProductionPackage(workflow),
    handoff: selectDirectorHandoff(workflow, draft, projectId, intelligenceSnapshot),
  }
}
