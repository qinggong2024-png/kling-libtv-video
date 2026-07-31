import { describe, expect, it } from 'vitest'
import {
  buildWaitingTasks,
  buildImageGenerationBatchRequest,
  calculateImageTaskSummary,
  compactImageAssetSet,
  createImageCenterDraft,
  getImageAssetSlots,
  getOrderedImageReferences,
  getOrderedSelectedTasks,
  imageAssetSetFromSlots,
  moveImageAssetSlot,
  normalizeImageGenerationModes,
  parseStoryboardPrompt,
  swapImageAssetSlots,
  validateImageCenterDraft,
} from './imageCenterModel'

function image(name: string): File {
  return new File(['image'], name, { type: 'image/jpeg' })
}

describe('image center model', () => {
  it('normalizes legacy generation modes to one mutually exclusive task', () => {
    expect(normalizeImageGenerationModes(['storyboard', 'fusion'])).toEqual(['storyboard'])
    expect(normalizeImageGenerationModes([])).toEqual(['fusion'])

    const draft = createImageCenterDraft('batch', 'outfit')
    draft.config.modes = ['fusion', 'storyboard']
    expect(validateImageCenterDraft(draft)).toContain('请选择且只能选择一种生成任务。')
  })

  it('treats back and side images as optional', () => {
    const draft = createImageCenterDraft('batch', 'outfit')
    draft.model.front = image('model-front.jpg')
    draft.outfits[0].front = image('product-front.jpg')
    draft.config.fusionPrompt = '保持服装准确'

    expect(validateImageCenterDraft(draft)).toEqual([])
  })

  it('parses one storyboard paragraph into ordered shots', () => {
    expect(parseStoryboardPrompt('模特走向镜头，展示服装正面，随后转身展示背面，最后拍摄面料细节。'))
      .toMatchObject([
        { order: 1, instruction: '模特走向镜头' },
        { order: 2, instruction: '展示服装正面' },
        { order: 3, instruction: '转身展示背面' },
        { order: 4, instruction: '拍摄面料细节' },
      ])
  })

  it('keeps a generate-one-image storyboard preset as one shot', () => {
    const prompt = '根据图一的人物和环境，生成一张人物别的姿势和拍摄角度的图片，正面与图二一致，背面与图三一致'

    expect(parseStoryboardPrompt(prompt)).toEqual([
      { id: 'shot-1', order: 1, instruction: prompt },
    ])
  })

  it('requires the product back image when the storyboard prompt references figure three', () => {
    const draft = createImageCenterDraft('batch', 'outfit')
    draft.model.front = image('model-front.jpg')
    draft.outfits[0].front = image('product-front.jpg')
    draft.config.modes = ['storyboard']
    draft.config.storyboardPrompt = '根据图一生成一张图片，正面与图二一致，背面与图三一致'

    expect(validateImageCenterDraft(draft)).toContain('当前分镜提示词引用图三，请为每套已就绪产品上传球衣背面图。')

    draft.outfits[0].back = image('product-back.jpg')
    expect(validateImageCenterDraft(draft)).toEqual([])
  })

  it('calculates fusion and storyboard output volume for all ready outfits', () => {
    const draft = createImageCenterDraft('batch', 'outfit-1')
    draft.model.front = image('model-front.jpg')
    draft.model.back = image('model-back.jpg')
    draft.outfits[0].front = image('product-1-front.jpg')
    draft.outfits[0].back = image('product-1-back.jpg')
    draft.outfits.push({
      id: 'outfit-2',
      name: '套装 02',
      sku: '',
      promptOverride: '',
      front: image('product-2-front.jpg'),
      back: null,
      side: null,
    })
    draft.config.modes = ['fusion', 'storyboard']
    draft.config.resultCount = 2
    draft.config.storyboardPrompt = '正面全身。背面展示。细节特写。'

    expect(calculateImageTaskSummary(draft)).toEqual({
      outfitCount: 2,
      fusionImages: 8,
      storyboardImages: 12,
      totalImages: 20,
      storyboardShotCount: 3,
      inferredBackOutfitCount: 1,
    })
  })

  it('creates one independent image task for each outfit', () => {
    const draft = createImageCenterDraft('batch', 'outfit-1')
    draft.model.front = image('model-front.jpg')
    draft.outfits[0].front = image('product-front.jpg')
    draft.config.fusionPrompt = '保持服装准确。'
    draft.outfits.push({
      id: 'outfit-2',
      name: '第二套',
      sku: 'SKU-2',
      promptOverride: '单独提示词',
      front: image('second-front.jpg'),
      back: null,
      side: null,
    })
    let nextId = 0
    const tasks = buildWaitingTasks(draft, () => `task-${++nextId}`, '2026-07-31T00:00:00.000Z')

    expect(tasks).toHaveLength(2)
    expect(tasks.map((task) => task.outfitId)).toEqual(['outfit-1', 'outfit-2'])
    expect(tasks[1].prompt.fusion).toBe(`${draft.config.fusionPrompt}\n单独提示词`)
    expect(tasks.every((task) => task.status === 'uploading')).toBe(true)
    expect(tasks[0]).toMatchObject({
      aspectRatio: '9:16',
      resolution: '2k',
      quality: 'medium',
      outputFormat: 'png',
      modelId: 'google/nano-banana-2/edit',
    })
  })

  it('groups selected outputs by product while preserving the storyboard order', () => {
    const draft = createImageCenterDraft('batch', 'outfit-1')
    draft.model.front = image('model-front.jpg')
    draft.outfits[0].front = image('product-1-front.jpg')
    draft.outfits.push({ id: 'outfit-2', name: '第二套', sku: 'SKU-2', promptOverride: '', front: image('product-2-front.jpg'), back: null, side: null })
    let nextId = 0
    const tasks = buildWaitingTasks(draft, () => `task-${++nextId}`)
    tasks[0].outputs = [
      { id: 'frame-a', kind: 'storyboard', view: 'shot', label: '分镜 A', file: null, url: 'a.png' },
      { id: 'frame-b', kind: 'storyboard', view: 'shot', label: '分镜 B', file: null, url: 'b.png' },
    ]
    tasks[1].outputs = [{ id: 'frame-c', kind: 'storyboard', view: 'shot', label: '分镜 C', file: null, url: 'c.png' }]

    const groups = getOrderedSelectedTasks(tasks, ['frame-b', 'frame-c', 'frame-a'])

    expect(groups.map(({ task }) => task.outfitId)).toEqual(['outfit-1', 'outfit-2'])
    expect(groups[0].outputs.map((output) => output.id)).toEqual(['frame-b', 'frame-a'])
    expect(groups[1].outputs.map((output) => output.id)).toEqual(['frame-c'])
  })

  it('keeps front, back and side images in explicit sortable slots', () => {
    const front = image('front.jpg')
    const back = image('back.jpg')
    const side = image('side.jpg')
    const assets = imageAssetSetFromSlots([front, back, side])

    expect(getImageAssetSlots(assets)).toEqual([front, back, side])
    expect(getImageAssetSlots(swapImageAssetSlots(assets, 0, 2))).toEqual([side, back, front])
    expect(swapImageAssetSlots(assets, -1, 2)).toBe(assets)
  })

  it('moves images with the same insertion behavior as storyboard sorting', () => {
    const front = image('front.jpg')
    const back = image('back.jpg')
    const side = image('side.jpg')
    const assets = imageAssetSetFromSlots([front, back, side])

    expect(getImageAssetSlots(moveImageAssetSlot(assets, 0, 2))).toEqual([back, side, front])
    expect(getImageAssetSlots(moveImageAssetSlot(assets, 2, 1))).toEqual([front, side, back])
    expect(moveImageAssetSlot(assets, 3, 0)).toBe(assets)
  })

  it('compacts legacy sparse slots into the new ordered upload list', () => {
    const front = image('front.jpg')
    const side = image('side.jpg')

    expect(getImageAssetSlots(compactImageAssetSet({ front, back: null, side }))).toEqual([front, side, null])
  })

  it('orders provider references explicitly across model and product images', () => {
    const model = {
      front: image('model-front.jpg'),
      back: image('model-back.jpg'),
      side: image('model-side.jpg'),
    }
    const product = {
      front: image('product-front.jpg'),
      back: image('product-back.jpg'),
      side: image('product-side.jpg'),
    }

    expect(getOrderedImageReferences(model, product).map(({ role, file }) => [role, file.name])).toEqual([
      ['model.front', 'model-front.jpg'],
      ['product.front', 'product-front.jpg'],
      ['product.back', 'product-back.jpg'],
      ['model.back', 'model-back.jpg'],
      ['product.side', 'product-side.jpg'],
      ['model.side', 'model-side.jpg'],
    ])
  })

  it('uploads shared model files once while preserving per-outfit reference indexes', () => {
    const draft = createImageCenterDraft('batch', 'outfit-1')
    draft.model.front = image('model-front.jpg')
    draft.outfits[0].front = image('product-1.jpg')
    draft.outfits.push({
      id: 'outfit-2',
      name: '套装 02',
      sku: '',
      promptOverride: '',
      front: image('product-2.jpg'),
      back: null,
      side: null,
    })
    let nextId = 0
    const tasks = buildWaitingTasks(draft, () => `task-${++nextId}`)

    const { manifest, files } = buildImageGenerationBatchRequest({
      clientBatchId: 'client-batch',
      name: draft.name,
      tasks,
      expectedGenerationCount: 2,
    })

    expect(files.map((file) => file.name)).toEqual(['model-front.jpg', 'product-1.jpg', 'product-2.jpg'])
    expect(manifest.items[0].referenceFileIndexes).toEqual([0, 1])
    expect(manifest.items[1].referenceFileIndexes).toEqual([0, 2])
    expect(manifest.items[1].referenceRoles).toEqual([
      { fileIndex: 0, role: 'model.front' },
      { fileIndex: 2, role: 'product.front' },
    ])
  })

  it('blocks batches whose server-expanded output count exceeds the 40 image limit', () => {
    const draft = createImageCenterDraft('batch', 'outfit-1')
    draft.model.front = image('model-front.jpg')
    draft.model.back = image('model-back.jpg')
    draft.outfits[0].front = image('product-1-front.jpg')
    draft.outfits[0].back = image('product-1-back.jpg')
    draft.outfits.push({
      id: 'outfit-2',
      name: '套装 02',
      sku: '',
      promptOverride: '',
      front: image('product-2-front.jpg'),
      back: image('product-2-back.jpg'),
      side: null,
    })
    draft.config.modes = ['fusion', 'storyboard']
    draft.config.resultCount = 4
    draft.config.storyboardPrompt = '镜头一。镜头二。镜头三。镜头四。'

    expect(calculateImageTaskSummary(draft).totalImages).toBe(48)
    expect(validateImageCenterDraft(draft)).toContain('每个批次最多生成 40 张图片，请减少套装、镜头或结果数量。')
  })

  it('rejects Nano Banana outfits with more than four ordered references', () => {
    const draft = createImageCenterDraft('batch', 'outfit-1')
    draft.config.fusionPrompt = '保持服装准确。'
    draft.model = {
      front: image('model-front.jpg'),
      back: image('model-back.jpg'),
      side: image('model-side.jpg'),
    }
    Object.assign(draft.outfits[0], {
      front: image('product-front.jpg'),
      back: image('product-back.jpg'),
      side: image('product-side.jpg'),
    })

    expect(getOrderedImageReferences(draft.model, draft.outfits[0])).toHaveLength(6)
    expect(validateImageCenterDraft(draft)).toContain('套装 01共有超过 4 张参考图，Nano Banana 2 每套最多支持 4 张，请移除多余的背面或侧面图。')
  })
})
