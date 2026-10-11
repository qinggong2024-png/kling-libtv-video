import type { CreativeProject } from '../../creative-project/types'
import type { DirectorPlanningSnapshot, StudioHandoffContext } from './contracts'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isHandoff(value: unknown): value is StudioHandoffContext {
  if (!isRecord(value)) return false
  return value.source === 'director-studio'
    && typeof value.directionId === 'string'
    && typeof value.packageId === 'string'
    && typeof value.packageRevision === 'number'
    && value.shotId === 'FIRST_FRAME'
    && isRecord(value.references)
    && value.references.productFront === true
    && value.references.selectedDirection === true
    && value.references.productionPackage === true
}

export function readDirectorPlanningSnapshot(
  project: CreativeProject,
): DirectorPlanningSnapshot | null {
  const planning = project.metadata?.directorPlanning
  if (!isRecord(planning)) return null
  const handoff = isHandoff(planning.handoff) ? planning.handoff : null
  return {
    brief: isRecord(planning.brief)
      ? planning.brief as unknown as DirectorPlanningSnapshot['brief']
      : {
          productName: '',
          brandMode: 'generic',
          brandName: '',
          objective: '',
          audience: '',
          notes: '',
        },
    candidates: Array.isArray(planning.candidates)
      ? planning.candidates as DirectorPlanningSnapshot['candidates']
      : [],
    selectedDirectionId: planning.selectedDirectionId === 'A'
      || planning.selectedDirectionId === 'B'
      || planning.selectedDirectionId === 'C'
      ? planning.selectedDirectionId
      : null,
    productionPackage: isRecord(planning.productionPackage)
      ? planning.productionPackage as unknown as DirectorPlanningSnapshot['productionPackage']
      : null,
    handoff,
  }
}

export function selectDirectorHandoffFromProject(
  project: CreativeProject,
): StudioHandoffContext | null {
  return readDirectorPlanningSnapshot(project)?.handoff ?? null
}
