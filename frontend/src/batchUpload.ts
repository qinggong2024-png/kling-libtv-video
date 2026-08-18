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

const PRODUCT_SUFFIX = /^(.*?)(?:[_\-\s]*(product|prod|商品|front|正面|正|前面|前|back|背面|背|后面|后))$/i
const STORYBOARD_PATTERNS = [
  /^(.*?)[(（]\s*(\d{1,2})\s*[)）]$/i,
  /^(.*?)[_\-\s]+(?:storyboard|shot|s|分镜)[_\-\s]*(\d{1,2})$/i,
  /^(.*?)[_\-\s]+(\d{1,2})$/i,
  /^(.*?)第\s*([一二三四五六七八九十\d]{1,3})\s*(?:张|幅|个)?$/i,
]
const BACK_MARKERS = new Set(['back', '背', '背面', '后', '后面'])
const CHINESE_DIGITS: Record<string, number> = { 一: 1, 二: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8, 九: 9 }

function stem(file: File): string {
  return file.name.replace(/\.[^.]+$/, '').trim()
}

function parseOrder(token: string): number | null {
  if (/^\d+$/.test(token)) return Number(token)
  if (token === '十') return 10
  const [tens, ones] = token.split('十')
  if (!token.includes('十')) return CHINESE_DIGITS[token] ?? null
  const value = (tens ? CHINESE_DIGITS[tens] : 1) * 10 + (ones ? CHINESE_DIGITS[ones] : 0)
  return Number.isFinite(value) ? value : null
}

function parseStoryboardName(name: string): { key: string; order: number } | null {
  for (const pattern of STORYBOARD_PATTERNS) {
    const match = name.match(pattern)
    const order = match ? parseOrder(match[2]) : null
    const key = match?.[1]?.replace(/[_\-\s]+$/, '').trim() ?? ''
    if (key && order !== null && order > 0) return { key, order }
  }
  return null
}

export function groupBatchUploadFiles(files: File[]): BatchUploadResult {
  const groups = new Map<string, BatchUploadGroup>()
  const storyboardOrders = new Map<string, Map<number, string>>()
  const rejected: string[] = []

  for (const file of files) {
    if (!isSupportedImageFile(file)) {
      rejected.push(file.name)
      continue
    }
    const name = stem(file)
    const storyboardMatch = parseStoryboardName(name)
    const productMatch = name.match(PRODUCT_SUFFIX)
    if (!storyboardMatch && !productMatch) {
      rejected.push(file.name)
      continue
    }
    const key = (storyboardMatch?.key ?? productMatch?.[1] ?? '').replace(/[_\-\s]+$/, '').trim()
    if (!key) {
      rejected.push(file.name)
      continue
    }
    const group = groups.get(key) ?? { key, productFront: null, productBack: null, storyboards: [], errors: [] }
    if (storyboardMatch) {
      const orders = storyboardOrders.get(key) ?? new Map<number, string>()
      const existing = orders.get(storyboardMatch.order)
      if (existing) group.errors.push(`分镜序号 ${storyboardMatch.order} 重复：${existing}、${file.name}`)
      else {
        orders.set(storyboardMatch.order, file.name)
        group.storyboards.push(file)
      }
      storyboardOrders.set(key, orders)
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
    group.storyboards.sort((a, b) => (parseStoryboardName(stem(a))?.order ?? 0) - (parseStoryboardName(stem(b))?.order ?? 0))
    if (!group.productFront) group.errors.push('缺少“品牌款号正”产品正面图')
    if (!group.storyboards.length) group.errors.push('缺少“品牌款号(1)”等分镜图')
  }

  return { groups: [...groups.values()].sort((a, b) => a.key.localeCompare(b.key)), rejected }
}
