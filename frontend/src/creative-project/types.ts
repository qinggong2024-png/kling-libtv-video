import type {
  CameraDNA,
  CharacterDNA,
  RealityEngineExecutionMode,
  RealitySnapshot,
  SceneDNA,
  StyleDNA,
} from './reality'

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
  creativeTaskId?: string
  activeProductId?: string
  activeProductVersionId?: string
  planningSnapshotRevision?: number
  currentStage?: string
}

export interface CreativeTaskRecoveryReference {
  schemaVersion: 1
  creative_task_id: string
  product_reference: {
    product_id?: string
    product_version_id?: string
    source_sha256?: string
  }
  planning_snapshot_index: {
    state_version: number
    package_revision?: number
    saved_at: string
  }
}

export interface CreativeIntelligenceSnapshot {
  realityEngineMode?: RealityEngineExecutionMode
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
  characterDNA?: CharacterDNA
  sceneDNA?: SceneDNA
  cameraDNA?: CameraDNA
  styleDNA?: StyleDNA
  realitySnapshot?: RealitySnapshot
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
