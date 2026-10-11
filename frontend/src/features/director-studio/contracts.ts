import type { CreativeIntelligenceSnapshot } from '../../creative-project/types'

export type DirectorDirectionId = 'A' | 'B' | 'C'

export interface CreativeBrief {
  productName: string
  brandMode: 'brand' | 'generic'
  brandName: string
  objective: string
  audience: string
  notes: string
}

export interface DirectionCandidate {
  id: DirectorDirectionId
  title: string
  summary: string
  human: string
  scene: string
  behavior: string
  camera: string
  emotion: string
}

export interface ProductionPackage {
  packageId: string
  revision: number
  parentPackageId: string | null
  locksHash: string
  factsRevision: number
  preservationHash: string
  ruleset: string
  shotId: 'FIRST_FRAME'
  prompt: string
  reality: Array<{ dimension: string; decision: string; evidence: string }>
}

export interface StudioHandoffContext {
  source: 'director-studio'
  projectId?: string
  directionId: DirectorDirectionId
  packageId: string
  packageRevision: number
  shotId: 'FIRST_FRAME'
  intelligenceSnapshot?: CreativeIntelligenceSnapshot
  references: {
    productFront: boolean
    selectedDirection: boolean
    productionPackage: boolean
  }
}

export interface DirectorPlanningSnapshot {
  brief: CreativeBrief
  candidates: DirectionCandidate[]
  selectedDirectionId: DirectorDirectionId | null
  productionPackage: ProductionPackage | null
  handoff: StudioHandoffContext | null
}
