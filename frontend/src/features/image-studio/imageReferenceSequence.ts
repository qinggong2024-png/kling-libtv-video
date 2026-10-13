import type { ImageAssetSet } from '../../imageCenterModel'

// Preserve the existing manifest's fixed reference order behind the unified upload UI.
export function bindImageReferenceSequence(files: readonly File[]): { model: ImageAssetSet; product: ImageAssetSet } {
  return {
    model: { front: files[0] ?? null, back: files[3] ?? null, side: files[5] ?? null },
    product: { front: files[1] ?? null, back: files[2] ?? null, side: files[4] ?? null },
  }
}
