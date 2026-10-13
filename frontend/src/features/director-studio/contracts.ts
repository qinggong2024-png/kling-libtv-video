import type { CreativeIntelligenceSnapshot } from '../../creative-project/types'
import type {
  DirectorCandidate,
  DirectorLatestReview,
  DirectorProductionPackage,
  DirectorSelection,
} from './directorApi'

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
  shotId: 'FIRST_FRAME' | 'SHOT_01'
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
  directorFixed?: {
    creativeTaskId: string
    sourceImageHash?: string
    package?: DirectorProductionPackage
    selection?: DirectorSelection
    shotMapping?: unknown
    storyboard?: {
      packages: Record<string, DirectorProductionPackage>
      candidates: DirectorCandidate[]
      selections: Record<string, DirectorSelection>
      latest_reviews: Record<string, DirectorLatestReview>
      shotMappings?: Record<string, unknown>
    }
  }
}
