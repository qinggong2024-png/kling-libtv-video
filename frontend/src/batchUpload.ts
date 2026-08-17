import { isSupportedImageFile } from './imageFiles'

export interface BatchUploadGroup {
  key: string
  product: File | null
  storyboards: File[]
  errors: string[]
}

export interface BatchUploadResult {
  groups: BatchUploadGroup[]
  rejected: string[]
}

const PRODUCT_SUFFIX = /^(.*?)(?:[_-](?:product|prod|商品))$/i
const STORYBOARD_SUFFIX = /^(.*?)(?:[_-](?:storyboard|shot|s|分镜)[_-]?(\d{1,2}))$/i

function stem(file: File): string {
  return file.name.replace(/\.[^.]+$/, '').trim()
}

export function groupBatchUploadFiles(files: File[]): BatchUploadResult {
  const groups = new Map<string, BatchUploadGroup>()
  const rejected: string[] = []

  for (const file of files) {
    if (!isSupportedImageFile(file)) {
      rejected.push(file.name)
      continue
    }
    const name = stem(file)
    const storyboardMatch = name.match(STORYBOARD_SUFFIX)
    const productMatch = name.match(PRODUCT_SUFFIX)
    if (!storyboardMatch && !productMatch) {
      rejected.push(file.name)
      continue
    }
    const key = (storyboardMatch?.[1] ?? productMatch?.[1] ?? '').trim()
    if (!key) {
      rejected.push(file.name)
      continue
    }
    const group = groups.get(key) ?? { key, product: null, storyboards: [], errors: [] }
    if (storyboardMatch) {
      group.storyboards.push(file)
    } else if (group.product) {
      group.errors.push(`产品图重复：${file.name}`)
    } else {
      group.product = file
    }
    groups.set(key, group)
  }

  for (const group of groups.values()) {
    group.storyboards.sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }))
    if (!group.product) group.errors.push('缺少 *_product 产品图')
    if (!group.storyboards.length) group.errors.push('缺少 *_s01、*_s02 等分镜图')
  }

  return { groups: [...groups.values()].sort((a, b) => a.key.localeCompare(b.key)), rejected }
}
