export type CreativeAssetKind =
  | 'product'
  | 'character'
  | 'scene'
  | 'template'
  | 'image'
  | 'video'
  | 'other'

export type CreativeAssetSource =
  | 'library'
  | 'upload'
  | 'task'
  | 'external'
  | 'unknown'

export interface AssetReference {
  id: string
  kind: CreativeAssetKind
  source: CreativeAssetSource
  label?: string
  revision?: number
  metadata?: Record<string, unknown>
}

export interface CreativeWorkflowContext {
  activeView?: string
  activeTaskId?: string
  currentStage?: string
}

export interface CreativeIntelligenceSnapshot {
  realityReference?: {
    realityDNAId?: string
  }
  spatialReference?: {
    spatialDNAId?: string
  }
  videoReference?: {
    videoDNAId?: string
  }
  referenceStrength?: number
}

export interface CreativeProject {
  id: string
  name?: string
  assets: AssetReference[]
  currentStage?: string
  metadata?: Record<string, unknown>
  revision?: number
  workflowContext?: CreativeWorkflowContext
  intelligenceSnapshot?: CreativeIntelligenceSnapshot
}
