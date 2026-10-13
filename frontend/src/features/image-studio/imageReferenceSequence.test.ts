import { describe, expect, it } from 'vitest'
import { buildImageGenerationBatchRequest, buildWaitingTasks, calculateImageTaskSummary, createImageCenterDraft, getOrderedImageReferences, IMAGE_REFERENCE_ROLE_ORDER, validateImageCenterDraft } from '../../imageCenterModel'
import { bindImageReferenceSequence } from './imageReferenceSequence'

const files = Array.from({ length: 6 }, (_, index) => new File([String(index)], `reference-${index + 1}.png`, { type: 'image/png' }))

function request(sequence: File[]) {
  const { model, product } = bindImageReferenceSequence(sequence)
  const draft = createImageCenterDraft('draft', 'outfit')
  draft.model = model
  draft.outfits[0] = { ...draft.outfits[0], ...product }
  draft.config.provider = 'gpt'
  draft.config.fusionPrompt = '保留参考图细节'
  return {
    draft,
    ...buildImageGenerationBatchRequest({
      clientBatchId: 'client-batch', name: draft.name, tasks: buildWaitingTasks(draft, () => 'task'),
      expectedGenerationCount: calculateImageTaskSummary(draft).totalImages,
    }),
  }
}

describe('unified reference sequence and existing generation contract', () => {
  it('keeps displayed order in multipart file indexes and the fixed role manifest', () => {
    const sequence = [files[3], files[0], files[5], files[1], files[4], files[2]]
    const result = request(sequence)
    expect(result.files).toEqual(sequence)
    expect(result.manifest.items[0].referenceRoles).toEqual(IMAGE_REFERENCE_ROLE_ORDER.map((role, fileIndex) => ({ role, fileIndex })))
    expect(getOrderedImageReferences(result.draft.model, result.draft.outfits[0]).map(({ file }) => file)).toEqual(sequence)
    expect(validateImageCenterDraft(result.draft)).toEqual([])
  })

  it('clears removed slots and compacts the remaining order without stale references', () => {
    const result = request([files[4], files[2], files[0]])
    expect(result.files).toEqual([files[4], files[2], files[0]])
    expect(result.draft.model).toEqual({ front: files[4], back: null, side: null })
    expect(result.draft.outfits[0]).toMatchObject({ front: files[2], back: files[0], side: null })
    expect(result.manifest.expectedGenerationCount).toBe(calculateImageTaskSummary(result.draft).totalImages)
  })

  it('preserves the required two references and Nano Banana maximum', () => {
    expect(bindImageReferenceSequence([])).toEqual({
      model: { front: null, back: null, side: null }, product: { front: null, back: null, side: null },
    })
    const two = request(files.slice(0, 2))
    expect(validateImageCenterDraft(two.draft)).toEqual([])
    const many = request(files)
    many.draft.config.provider = 'nanobanana'
    expect(validateImageCenterDraft(many.draft).some(error => error.includes('最多支持 4 张'))).toBe(true)
    expect(getOrderedImageReferences(many.draft.model, many.draft.outfits[0])).toHaveLength(6)
  })
})
