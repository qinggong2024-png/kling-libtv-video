import { isSupportedImageFile } from './imageFiles'

export interface BatchUploadGroup {
  key: string
  productFront: File | null
  productBack: File | null
  storyboards: File[]
  errors: string[]
}

export interface BatchUploadResult {
  groups: BatchUploadGroup[]
  rejected: string[]
}

const PRODUCT_SUFFIX = /^(.*?)(?:[_-]?(product|prod|商品|front|正面|正|back|背面|背))$/i
const STORYBOARD_SUFFIX = /^(.*?)(?:\((\d{1,2})\)|[_-](?:storyboard|shot|s|分镜)[_-]?(\d{1,2}))$/i
const BACK_MARKERS = new Set(['back', '背', '背面'])

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
    const group = groups.get(key) ?? { key, productFront: null, productBack: null, storyboards: [], errors: [] }
    if (storyboardMatch) {
      group.storyboards.push(file)
    } else {
      const isBack = BACK_MARKERS.has(productMatch?.[2]?.toLowerCase() ?? '')
      if (isBack) {
        if (group.productBack) group.errors.push(`产品背面图重复：${file.name}`)
        else group.productBack = file
      } else if (group.productFront) {
        group.errors.push(`产品正面图重复：${file.name}`)
      } else {
        group.productFront = file
      }
    }
    groups.set(key, group)
  }

  for (const group of groups.values()) {
    group.storyboards.sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }))
    if (!group.productFront) group.errors.push('缺少“品牌款号正”产品正面图')
    if (!group.storyboards.length) group.errors.push('缺少“品牌款号(1)”等分镜图')
  }

  return { groups: [...groups.values()].sort((a, b) => a.key.localeCompare(b.key)), rejected }
}
