import type { DirectorDirection, DirectorProductIntake } from './directorModel'
import type { DirectorDirectionId, DirectionCandidate, CreativeBrief, ProductionPackage } from './contracts'

export function toCreativeBrief(intake: DirectorProductIntake): CreativeBrief {
  return {
    productName: intake.productName,
    brandMode: intake.brandMode,
    brandName: intake.brandName,
    objective: intake.objective,
    audience: intake.audience,
    notes: intake.notes,
  }
}

export function toDirectionCandidate(direction: DirectorDirection): DirectionCandidate {
  return { ...direction }
}

export function toDirectionCandidates(directions: DirectorDirection[]): DirectionCandidate[] {
  return directions.map(toDirectionCandidate)
}

export function toProductionPackage(
  packageRevision: {
    package_id: string
    revision: number
    parent_package_id: string | null
    locks_hash: string
    facts_revision: number
    preservation_hash: string
    ruleset: string
    purpose?: 'FIRST_FRAME' | 'VIDEO_STORYBOARD'
    shot_id: 'FIRST_FRAME' | 'SHOT_01'
    prompt: string
    reality: Array<{ dimension: string; decision: string; evidence: string }>
  },
): ProductionPackage {
  return {
    packageId: packageRevision.package_id,
    revision: packageRevision.revision,
    parentPackageId: packageRevision.parent_package_id,
    locksHash: packageRevision.locks_hash,
    factsRevision: packageRevision.facts_revision,
    preservationHash: packageRevision.preservation_hash,
    ruleset: packageRevision.ruleset,
    shotId: packageRevision.shot_id,
    prompt: packageRevision.prompt,
    reality: packageRevision.reality,
  }
}

export function directionId(value: string): DirectorDirectionId | null {
  return value === 'A' || value === 'B' || value === 'C' ? value : null
}
