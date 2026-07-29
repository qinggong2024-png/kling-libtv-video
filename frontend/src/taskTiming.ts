const EXPLICIT_TIMEZONE = /(Z|[+-]\d{2}:\d{2})$/i

export function parseTaskTimestamp(value: string): number {
  const normalized = EXPLICIT_TIMEZONE.test(value) ? value : `${value}Z`
  return new Date(normalized).getTime()
}

export function formatElapsed(value: string, endValue: string | number = Date.now()): string {
  const startTime = parseTaskTimestamp(value)
  const endTime = typeof endValue === 'number' ? endValue : parseTaskTimestamp(endValue)
  if (!Number.isFinite(startTime) || !Number.isFinite(endTime)) return '—'

  const seconds = Math.max(0, Math.floor((endTime - startTime) / 1000))
  if (seconds < 60) return `${seconds} 秒`
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟`

  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  return minutes ? `${hours} 小时 ${minutes} 分钟` : `${hours} 小时`
}

export function formatDurationSeconds(value: number): string {
  const seconds = Math.max(0, Math.floor(value))
  if (seconds < 60) return `${seconds} 秒`
  if (seconds < 3600) {
    const minutes = Math.floor(seconds / 60)
    const remainder = seconds % 60
    return remainder ? `${minutes} 分 ${remainder} 秒` : `${minutes} 分钟`
  }

  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  return minutes ? `${hours} 小时 ${minutes} 分` : `${hours} 小时`
}
