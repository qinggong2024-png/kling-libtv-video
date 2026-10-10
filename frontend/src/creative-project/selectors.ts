import type { AssetReference, CreativeProject } from './types'

export function selectProjectAssets(project: CreativeProject): readonly AssetReference[] {
  return project.assets
}

export function selectProjectAsset(project: CreativeProject, assetId: string): AssetReference | null {
  return project.assets.find((asset) => asset.id === assetId) ?? null
}

export function selectProjectStage(project: CreativeProject): string | null {
  return project.currentStage ?? project.workflowContext?.currentStage ?? null
}

export function selectProjectTaskId(project: CreativeProject): string | null {
  return project.workflowContext?.activeTaskId ?? null
}

export function selectCreativeIntelligenceSnapshot(project: CreativeProject) {
  return project.intelligenceSnapshot ?? null
}
