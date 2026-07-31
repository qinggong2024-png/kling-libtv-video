import type { ImageGenerationClientManifest } from './types'

export type ImageCenterTab = 'create' | 'results'
export type ImageProvider = 'gpt' | 'nanobanana'
export type ImageGenerationMode = 'fusion' | 'storyboard'
export type ImageTaskStatus = 'uploading' | 'submitting' | 'queued' | 'running' | 'completed' | 'failed' | 'write_uncertain'
export type ImageOutputKind = 'fusion' | 'storyboard'
export type ImageOutputView = 'front' | 'back' | 'shot'

export interface ImageAssetSet {
  front: File | null
  back: File | null
  side: File | null
}

export interface OutfitDraft extends ImageAssetSet {
  id: string
  name: string
  sku: string
  promptOverride: string
}

export interface ImageCenterConfig {
  provider: ImageProvider
  modes: ImageGenerationMode[]
  resultCount: 1 | 2 | 3 | 4
  fusionPrompt: string
  storyboardPrompt: string
  allowBackInference: boolean
  aspectRatio: string
  resolution: string
  quality: 'low' | 'medium' | 'high'
  outputFormat: 'png'
}

export interface ImageGenerationOutput {
  id: string
  kind: ImageOutputKind
  view: ImageOutputView
  label: string
  file: File | null
  url: string
  downloadUrl?: string | null
  artifactId?: string | null
}

export interface ImageGenerationTask {
  id: string
  outfitId: string
  outfitName: string
  sku: string
  provider: ImageProvider
  modes: ImageGenerationMode[]
  resultCount: 1 | 2 | 3 | 4
  aspectRatio: string
  resolution: string
  quality: 'low' | 'medium' | 'high'
  outputFormat: 'png'
  allowBackInference: boolean
  storyboardShots: StoryboardShot[]
  status: ImageTaskStatus
  batchId: string | null
  providerTaskId: string | null
  providerTaskIds: string[]
  modelId: string
  createdAt: string
  prompt: {
    fusion: string
    storyboard: string
  }
  model: ImageAssetSet
  product: ImageAssetSet
  outputs: ImageGenerationOutput[]
  error: string
  errorCode: string | null
  retryable: boolean | null
  errorDetails?: unknown
}

export function getOrderedSelectedTasks(tasks: ImageGenerationTask[], selectedOutputIds: string[]) {
  const selectedOrder = new Map(selectedOutputIds.map((id, index) => [id, index]))
  return tasks.map((task) => ({
    task,
    outputs: task.outputs.filter((output) => selectedOrder.has(output.id)).sort((left, right) => selectedOrder.get(left.id)! - selectedOrder.get(right.id)!),
  })).filter((item) => item.outputs.length)
}

export interface ImageCenterDraft {
  version: 1
  id: string
  name: string
  activeTab: ImageCenterTab
  model: ImageAssetSet
  outfits: OutfitDraft[]
  config: ImageCenterConfig
  tasks: ImageGenerationTask[]
  selectedOutputIds: string[]
  updatedAt: string
}

export interface StoryboardShot {
  id: string
  order: number
  instruction: string
}

export interface ImageTaskSummary {
  outfitCount: number
  fusionImages: number
  storyboardImages: number
  totalImages: number
  storyboardShotCount: number
  inferredBackOutfitCount: number
}

export const MAX_IMAGE_CENTER_OUTFITS = 20
export const MAX_IMAGE_GENERATIONS_PER_BATCH = 40
export const IMAGE_ASSET_SLOT_LABELS = ['正面', '背面', '侧面'] as const

export function createEmptyImageAssetSet(): ImageAssetSet {
  return { front: null, back: null, side: null }
}

export function getImageAssetSlots(assets: ImageAssetSet): [File | null, File | null, File | null] {
  return [assets.front, assets.back, assets.side]
}

export function imageAssetSetFromSlots(slots: readonly (File | null)[]): ImageAssetSet {
  return {
    front: slots[0] ?? null,
    back: slots[1] ?? null,
    side: slots[2] ?? null,
  }
}

export function compactImageAssetSet(assets: ImageAssetSet): ImageAssetSet {
  return imageAssetSetFromSlots(getImageAssetSlots(assets).filter((file): file is File => file !== null))
}

export function swapImageAssetSlots(assets: ImageAssetSet, from: number, to: number): ImageAssetSet {
  if (from === to || from < 0 || from > 2 || to < 0 || to > 2) return assets
  const slots = getImageAssetSlots(assets)
  ;[slots[from], slots[to]] = [slots[to], slots[from]]
  return imageAssetSetFromSlots(slots)
}

export function moveImageAssetSlot(assets: ImageAssetSet, from: number, to: number): ImageAssetSet {
  const files = getImageAssetSlots(assets).filter((file): file is File => file !== null)
  if (from === to || from < 0 || from >= files.length || to < 0 || to > files.length) return assets
  const next = [...files]
  const [moved] = next.splice(from, 1)
  next.splice(Math.min(to, next.length), 0, moved)
  return imageAssetSetFromSlots(next)
}

export function createOutfit(id: string, index: number): OutfitDraft {
  return {
    id,
    name: `套装 ${String(index).padStart(2, '0')}`,
    sku: '',
    promptOverride: '',
    ...createEmptyImageAssetSet(),
  }
}

export function normalizeImageGenerationModes(
  modes: readonly ImageGenerationMode[] | null | undefined,
): [ImageGenerationMode] {
  const mode = modes?.find((item) => item === 'fusion' || item === 'storyboard')
  return [mode ?? 'fusion']
}

export function createImageCenterDraft(id: string, outfitId: string, now = new Date().toISOString()): ImageCenterDraft {
  return {
    version: 1,
    id,
    name: '未命名图片批次',
    activeTab: 'create',
    model: createEmptyImageAssetSet(),
    outfits: [createOutfit(outfitId, 1)],
    config: {
      provider: 'nanobanana',
      modes: ['fusion'],
      resultCount: 1,
      fusionPrompt: '',
      storyboardPrompt: '',
      allowBackInference: true,
      aspectRatio: '9:16',
      resolution: '2k',
      quality: 'medium',
      outputFormat: 'png',
    },
    tasks: [],
    selectedOutputIds: [],
    updatedAt: now,
  }
}

export function parseStoryboardPrompt(prompt: string): StoryboardShot[] {
  const normalized = prompt.trim().replace(/\s+/g, ' ')
  if (!normalized) return []

  if (normalized.includes('生成一张')) {
    return [{ id: 'shot-1', order: 1, instruction: normalized }]
  }

  let parts = normalized
    .split(/[。！？!?；;\n]+/)
    .map((part) => part.trim())
    .filter(Boolean)

  if (parts.length === 1) {
    parts = normalized
      .split(/(?:，|,|然后|随后|最后|再拍|接着)/)
      .map((part) => part.trim().replace(/[。！？!?；;]+$/g, ''))
      .filter((part) => part.length >= 2)
  }

  return parts.slice(0, 7).map((instruction, index) => ({
    id: `shot-${index + 1}`,
    order: index + 1,
    instruction,
  }))
}

export function outfitCanGenerateBack(model: ImageAssetSet, outfit: ImageAssetSet, allowInference: boolean): boolean {
  if (model.back && outfit.back) return true
  return allowInference && Boolean(model.back || outfit.back)
}

export function calculateImageTaskSummary(draft: ImageCenterDraft): ImageTaskSummary {
  const readyOutfits = draft.outfits.filter((outfit) => outfit.front)
  const storyboardShotCount = draft.config.modes.includes('storyboard')
    ? parseStoryboardPrompt(draft.config.storyboardPrompt).length
    : 0
  let fusionImages = 0
  let inferredBackOutfitCount = 0

  if (draft.config.modes.includes('fusion')) {
    for (const outfit of readyOutfits) {
      const hasExactBack = Boolean(draft.model.back && outfit.back)
      const generatesBack = outfitCanGenerateBack(draft.model, outfit, draft.config.allowBackInference)
      fusionImages += (1 + Number(generatesBack)) * draft.config.resultCount
      if (generatesBack && !hasExactBack) inferredBackOutfitCount += 1
    }
  }

  const storyboardImages = draft.config.modes.includes('storyboard')
    ? readyOutfits.length * storyboardShotCount * draft.config.resultCount
    : 0

  return {
    outfitCount: readyOutfits.length,
    fusionImages,
    storyboardImages,
    totalImages: fusionImages + storyboardImages,
    storyboardShotCount,
    inferredBackOutfitCount,
  }
}

export function validateImageCenterDraft(draft: ImageCenterDraft): string[] {
  const errors: string[] = []
  if (!draft.model.front) errors.push('请上传模特正面图。')
  if (!draft.outfits.some((outfit) => outfit.front)) errors.push('请至少上传一套产品正面图。')
  if (draft.config.modes.length !== 1) errors.push('请选择且只能选择一种生成任务。')
  if (draft.config.modes.includes('fusion') && !draft.config.fusionPrompt.trim()) errors.push('请填写多图融合提示词。')
  if (draft.config.modes.includes('storyboard') && !draft.config.storyboardPrompt.trim()) errors.push('请填写分镜图提示词。')
  if (draft.config.modes.includes('storyboard') && draft.config.storyboardPrompt.includes('图三') && draft.outfits.some((outfit) => outfit.front && !outfit.back)) {
    errors.push('当前分镜提示词引用图三，请为每套已就绪产品上传球衣背面图。')
  }
  if (draft.config.modes.includes('storyboard') && draft.config.storyboardPrompt.trim() && !parseStoryboardPrompt(draft.config.storyboardPrompt).length) {
    errors.push('分镜提示词暂时无法拆分，请补充镜头描述。')
  }
  if (draft.config.provider === 'nanobanana') {
    const oversized = draft.outfits.find((outfit) => outfit.front && getOrderedImageReferences(draft.model, outfit).length > 4)
    if (oversized) errors.push(`${oversized.name.trim() || '未命名套装'}共有超过 4 张参考图，Nano Banana 2 每套最多支持 4 张，请移除多余的背面或侧面图。`)
  }
  if (draft.outfits.length > MAX_IMAGE_CENTER_OUTFITS) errors.push(`每个批次最多添加 ${MAX_IMAGE_CENTER_OUTFITS} 套产品。`)
  if (calculateImageTaskSummary(draft).totalImages > MAX_IMAGE_GENERATIONS_PER_BATCH) errors.push(`每个批次最多生成 ${MAX_IMAGE_GENERATIONS_PER_BATCH} 张图片，请减少套装、镜头或结果数量。`)
  return errors
}

export function buildWaitingTasks(
  draft: ImageCenterDraft,
  makeId: () => string,
  now = new Date().toISOString(),
): ImageGenerationTask[] {
  const appendOverride = (base: string, override: string) => [base.trim(), override.trim()].filter(Boolean).join('\n')
  return draft.outfits.filter((outfit) => outfit.front).map((outfit) => ({
    id: makeId(),
    outfitId: outfit.id,
    outfitName: outfit.name.trim() || '未命名套装',
    sku: outfit.sku.trim(),
    provider: draft.config.provider,
    modes: [...draft.config.modes],
    resultCount: draft.config.resultCount,
    aspectRatio: draft.config.aspectRatio,
    resolution: draft.config.resolution,
    quality: 'medium',
    outputFormat: draft.config.outputFormat,
    allowBackInference: draft.config.allowBackInference,
    storyboardShots: parseStoryboardPrompt(draft.config.storyboardPrompt),
    status: 'uploading',
    batchId: null,
    providerTaskId: null,
    providerTaskIds: [],
    modelId: draft.config.provider === 'gpt' ? 'openai/gpt-image-2/edit' : 'google/nano-banana-2/edit',
    createdAt: now,
    prompt: {
      fusion: appendOverride(draft.config.fusionPrompt, outfit.promptOverride),
      storyboard: appendOverride(draft.config.storyboardPrompt, outfit.promptOverride),
    },
    model: { ...draft.model },
    product: { front: outfit.front, back: outfit.back, side: outfit.side },
    outputs: [],
    error: '',
    errorCode: null,
    retryable: null,
  }))
}

export const IMAGE_REFERENCE_ROLE_ORDER = [
  'model.front',
  'product.front',
  'product.back',
  'model.back',
  'product.side',
  'model.side',
] as const

export type ImageReferenceRole = typeof IMAGE_REFERENCE_ROLE_ORDER[number]

export function getOrderedImageReferences(
  model: ImageAssetSet,
  product: ImageAssetSet,
): Array<{ role: ImageReferenceRole; file: File }> {
  const candidates: Record<ImageReferenceRole, File | null> = {
    'model.front': model.front,
    'product.front': product.front,
    'product.back': product.back,
    'model.back': model.back,
    'product.side': product.side,
    'model.side': model.side,
  }
  return IMAGE_REFERENCE_ROLE_ORDER.flatMap((role) => {
    const file = candidates[role]
    return file ? [{ role, file }] : []
  })
}

export function buildImageGenerationBatchRequest(options: {
  clientBatchId: string
  name: string
  tasks: ImageGenerationTask[]
  expectedGenerationCount: number
}): { manifest: ImageGenerationClientManifest; files: File[] } {
  const first = options.tasks[0]
  if (!first) throw new Error('at least one image generation task is required')
  const files: File[] = []
  const fileIndexes = new Map<File, number>()
  const items = options.tasks.map((task) => {
    const referenceRoles = getOrderedImageReferences(task.model, task.product).map(({ role, file }) => {
      let fileIndex = fileIndexes.get(file)
      if (fileIndex === undefined) {
        fileIndex = files.length
        files.push(file)
        fileIndexes.set(file, fileIndex)
      }
      return { fileIndex, role }
    })
    return {
      clientTaskId: task.id,
      outfitId: task.outfitId,
      outfitName: task.outfitName,
      sku: task.sku,
      prompts: task.prompt,
      storyboardShots: task.storyboardShots.map(({ order, instruction }) => ({ order, instruction })),
      referenceFileIndexes: referenceRoles.map(({ fileIndex }) => fileIndex),
      referenceRoles,
    }
  })
  return {
    files,
    manifest: {
      clientBatchId: options.clientBatchId,
      name: options.name,
      provider: first.provider,
      modes: first.modes,
      resultCount: first.resultCount,
      aspectRatio: first.aspectRatio,
      resolution: first.resolution,
      ...(first.provider === 'gpt' ? { quality: first.quality } : {}),
      outputFormat: 'png',
      allowBackInference: first.allowBackInference,
      paidSubmissionConsent: true,
      expectedGenerationCount: options.expectedGenerationCount,
      items,
    },
  }
}
