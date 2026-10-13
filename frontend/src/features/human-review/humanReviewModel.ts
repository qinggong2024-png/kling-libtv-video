import type { HumanReviewInput, HumanReviewQuery, HumanReviewReason, HumanReviewSubjectType } from './contracts'

export const imageReasons: ReadonlyArray<readonly [HumanReviewReason, string]> = [
  ['FACE', '人脸'], ['GARMENT', '服装'], ['REALISM', '真实感'],
  ['SPACE', '空间'], ['LIGHTING', '光线'], ['OTHER', '其他'],
]
export const videoReasons: ReadonlyArray<readonly [HumanReviewReason, string]> = [
  ['MOTION', '动作'], ['DEFORMATION', '变形'], ['CAMERA', '镜头'], ['OTHER', '其他'],
]

export function humanReviewReasons(type: HumanReviewSubjectType) {
  return type === 'VIDEO_VARIANT' ? videoReasons : imageReasons
}

export function humanReviewInputError(input: HumanReviewInput): string | null {
  if (typeof input.expectedOutputHash !== 'string' || !/^[0-9a-f]{64}$/.test(input.expectedOutputHash)) return '结果指纹尚未确认'
  if (input.subjectType === 'DIRECTOR_CANDIDATE' && !input.taskId) return '缺少导演任务'
  if (input.subjectType === 'VIDEO_VARIANT' && input.verdict === 'REWORK') return '视频评价不支持 REWORK'
  const allowed = new Set(humanReviewReasons(input.subjectType).map(([code]) => code))
  if (input.reasonCodes.some(code => !allowed.has(code))) return '原因与媒介类型不匹配'
  if (input.verdict === 'PASS' && input.reasonCodes.length) return 'PASS 不包含失败原因'
  if (input.verdict !== 'PASS' && !input.reasonCodes.length) return '请选择至少一个原因'
  if (input.reasonCodes.includes('OTHER') && !input.note.trim()) return 'OTHER 需要填写说明'
  if (input.note.length > 255) return '说明最多 255 字符'
  return null
}

export function humanReviewQueryString(query: HumanReviewQuery): string {
  const values = new URLSearchParams({ subjectType: query.subjectType, subjectId: query.subjectId })
  if (query.taskId) values.set('taskId', query.taskId)
  return values.toString()
}

function pendingKey(query: HumanReviewQuery) {
  return `libtv.human-review.pending.v1:${query.subjectType}:${query.taskId ?? ''}:${query.subjectId}`
}

export function readPendingHumanReview(query: HumanReviewQuery): HumanReviewInput | null {
  try {
    const raw = sessionStorage.getItem(pendingKey(query))
    if (!raw) return null
    const data = JSON.parse(raw) as { schemaVersion?: string; input?: HumanReviewInput }
    const input = data.input
    if (data.schemaVersion !== 'human-review-pending.v1' || !input || input.subjectType !== query.subjectType || input.subjectId !== query.subjectId || (input.taskId ?? '') !== (query.taskId ?? '') || typeof input.reviewKey !== 'string' || !input.reviewKey || !Array.isArray(input.reasonCodes) || typeof input.note !== 'string' || !['PASS', 'REWORK', 'FAIL'].includes(input.verdict) || humanReviewInputError(input)) return null
    return input
  } catch {
    return null
  }
}

export function persistPendingHumanReview(query: HumanReviewQuery, input: HumanReviewInput | null): boolean {
  try {
    if (input) sessionStorage.setItem(pendingKey(query), JSON.stringify({ schemaVersion: 'human-review-pending.v1', input }))
    else sessionStorage.removeItem(pendingKey(query))
    return true
  } catch {
    return false
  }
}
