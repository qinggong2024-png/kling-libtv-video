import type { DirectorTaskResponse } from './directorApi'

export const packageFields = [
  ['direction', '创意方向'],
  ['audience', '目标受众'],
  ['characterDNA', '人物设定'],
  ['sceneDNA', '场景设定'],
  ['cameraDNA', '镜头设定'],
  ['imagePrompt', '图片 Prompt'],
  ['videoPrompt', '视频 Prompt'],
  ['shotPlan', '分镜'],
  ['qualityChecklist', '人工检查项'],
] as const

export type CreativePackageDocument = Record<string, unknown> & {
  direction: unknown
  audience: unknown
  characterDNA: unknown
  sceneDNA: unknown
  cameraDNA: unknown
  imagePrompt: unknown
  videoPrompt: unknown
  shotPlan: unknown
  qualityChecklist: unknown
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

export function selectCreativePackageExport(workflow: DirectorTaskResponse | null, packageId: string): CreativePackageDocument | null {
  const response: unknown = workflow
  if (!isRecord(response) || !isRecord(response.creative_packages)) return null
  const document = response.creative_packages[packageId]
  if (!isRecord(document) || !packageFields.every(([key]) => key in document)) return null
  if (!isRecord(document.provenance) || document.provenance.schemaVersion !== 'creative-package.v1' || document.provenance.packageId !== packageId) return null
  return document as CreativePackageDocument
}

export function packageFieldText(value: unknown): string {
  if (value === null || value === undefined || value === '') return '未提供 · 待人工确认'
  return typeof value === 'string' ? value : JSON.stringify(value, null, 2)
}

export function creativePackageDisplayText(field: string, value: unknown): string {
  if (field === 'shotPlan' && Array.isArray(value)) {
    return value.map((shot: unknown) => isRecord(shot) ? `${shot.shotId ?? '未提供镜头'} · r${shot.revision ?? '?'}\n${shot.packageId ?? '未提供包标识'}` : packageFieldText(shot)).join('\n\n')
  }
  if (field === 'qualityChecklist' && Array.isArray(value)) {
    return value.map((item: unknown) => isRecord(item) ? `${item.dimension ?? '检查项'}: ${item.expectation ?? '未提供'} · 待人工检查` : packageFieldText(item)).join('\n')
  }
  if (field === 'direction' && isRecord(value)) {
    return [value.title, value.scene, value.behavior].filter((item) => typeof item === 'string').join('\n') || packageFieldText(value)
  }
  if (isRecord(value) && typeof value.description === 'string') return value.description
  if (field === 'characterDNA' && isRecord(value) && typeof value.behavior === 'string') {
    return `行为：${value.behavior}\n人物身份 / 外貌：${value.identity ?? '待人工确认'} / ${value.appearance ?? '待人工确认'}`
  }
  if (field === 'characterDNA' && isRecord(value) && typeof value.expressionLanguage === 'string') {
    return `${value.expressionLanguage || '人物风格待人工确认'}\n人物身份：待人工确认`
  }
  return packageFieldText(value)
}

export function creativePackageText(document: CreativePackageDocument): string {
  return [
    'Creative Package',
    ...packageFields.map(([key, label]) => `${label} (${key})\n${packageFieldText(document[key])}`),
    `来源与合同\n${JSON.stringify(Object.fromEntries(Object.entries(document).filter(([key]) => !packageFields.some(([field]) => field === key))), null, 2)}`,
  ].join('\n\n')
}

export function creativePackageJson(document: CreativePackageDocument): string {
  return JSON.stringify(document, null, 2)
}

export async function copyCreativePackage(text: string): Promise<void> {
  if (!globalThis.navigator?.clipboard?.writeText) throw new Error('CLIPBOARD_UNAVAILABLE')
  await navigator.clipboard.writeText(text)
}

export function downloadCreativePackage(document: CreativePackageDocument, packageId: string): void {
  const url = URL.createObjectURL(new Blob([creativePackageJson(document)], { type: 'application/json;charset=utf-8' }))
  const link = globalThis.document.createElement('a')
  link.href = url
  link.download = `creative-package-${packageId.replace(/[^a-zA-Z0-9_-]/g, '_')}.json`
  globalThis.document.body.appendChild(link)
  try {
    link.click()
  } finally {
    link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
}
