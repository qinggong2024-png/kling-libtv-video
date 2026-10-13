import type { DirectorTaskResponse } from './directorApi'

export const packageFields = [
  ['direction', '创意方向'],
  ['audience', '目标受众'],
  ['characterDNA', '人物设定'],
  ['sceneDNA', '场景设定'],
  ['cameraDNA', '镜头设定'],
  ['imagePrompt', '图片生成提示词'],
  ['videoPrompt', '视频创作提案'],
  ['shotPlan', '镜头规划'],
  ['qualityChecklist', '质量检查'],
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

export function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

export function creativePackageFieldStatus(document: CreativePackageDocument, field: string): string {
  if (document[field] === null || document[field] === undefined || document[field] === ''
    || (Array.isArray(document[field]) && document[field].length === 0)) return '未提供'
  const statuses = isRecord(document.fieldStatus) ? document.fieldStatus : {}
  if (statuses[field] === 'PROPOSED') return '创意提案 · 待人工确认'
  if (statuses[field] === 'UNRESOLVED') return '未提供 · 待补充'
  return statuses[field] === 'PRESENT' ? '已记录 · 未验证生产内容' : '状态未提供'
}

export function creativePackageFieldSource(document: CreativePackageDocument, field: string): string {
  const provenance = isRecord(document.provenance) ? document.provenance : {}
  const evidence = isRecord(provenance.originEvidence) ? provenance.originEvidence : {}
  const sources = isRecord(evidence.fieldSources) ? evidence.fieldSources : {}
  const source = typeof sources[field] === 'string' ? sources[field] : ''
  if (source.startsWith('proposed-video-handoff.')) return '方向与冻结包规则整理的交接提案'
  if (source.startsWith('plan.brand_dna.')) return '任务绑定的品牌上下文'
  if (source.startsWith('plan.directions')) return '已选择方向的提案记录'
  if (source.startsWith('package.reality')) return '冻结生产包中的规则记录'
  if (source === 'package.prompt') return '冻结生产包原文'
  if (source.startsWith('package.')) return '冻结生产包'
  if (source.startsWith('plan.')) return '任务规划记录'
  return '未提供'
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
