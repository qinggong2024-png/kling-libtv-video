export type KlingElementStatusGroup = 'available' | 'failed' | 'processing'

const AVAILABLE_STATUSES = new Set([
  'active',
  'completed',
  'ready',
  'succeed',
  'succeeded',
  'success',
])

const FAILED_STATUSES = new Set(['canceled', 'cancelled', 'error', 'failed'])

export function normalizeKlingElementStatus(status: string): string {
  return status.trim().toLowerCase()
}

export function getKlingElementStatusGroup(status: string): KlingElementStatusGroup {
  const normalized = normalizeKlingElementStatus(status)
  if (AVAILABLE_STATUSES.has(normalized)) return 'available'
  if (FAILED_STATUSES.has(normalized)) return 'failed'
  return 'processing'
}

export function isKlingElementAvailable(status: string): boolean {
  return getKlingElementStatusGroup(status) === 'available'
}

export function getKlingElementStatusLabel(status: string): string {
  const normalized = normalizeKlingElementStatus(status)
  const group = getKlingElementStatusGroup(normalized)
  if (group === 'available') return '可用'
  if (group === 'failed') return '失败'
  if (normalized === 'submitted') return '创建中'
  return '处理中'
}
