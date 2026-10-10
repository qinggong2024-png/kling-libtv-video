import type { AssetReference, CreativeAssetKind, CreativeAssetSource } from '../types'

export interface AssetReferenceInput {
  id: string
  kind?: CreativeAssetKind
  source?: CreativeAssetSource
  label?: string
  revision?: number
  metadata?: Record<string, unknown>
}

export function toAssetReference(input: AssetReferenceInput): AssetReference {
  return {
    id: input.id,
    kind: input.kind ?? 'other',
    source: input.source ?? 'unknown',
    ...(input.label ? { label: input.label } : {}),
    ...(input.revision === undefined ? {} : { revision: input.revision }),
    ...(input.metadata ? { metadata: input.metadata } : {}),
  }
}

export function mergeAssetReferences(
  current: readonly AssetReference[],
  incoming: readonly AssetReference[],
): AssetReference[] {
  const merged = new Map(current.map((asset) => [asset.id, asset]))
  for (const asset of incoming) merged.set(asset.id, asset)
  return [...merged.values()]
}
