import type { VideoGenerationStatus } from './types'

const FALLBACK_DURATIONS = Array.from({ length: 13 }, (_, index) => index + 3)

function parseDurationOptions(values: string[] | undefined): number[] {
  return [...new Set((values ?? [])
    .map(Number)
    .filter((value) => Number.isInteger(value) && value > 0))]
    .sort((left, right) => left - right)
}

export function getVideoDurationOptions(
  status: VideoGenerationStatus | null | undefined,
  storyboardCount: number,
): number[] {
  const configured = parseDurationOptions(
    storyboardCount >= 2 ? status?.tailImageVideoDurations : status?.videoDurations,
  )
  if (configured.length) return configured
  if (status?.backend === 'bach') {
    return Array.from({ length: storyboardCount >= 2 ? 6 : 8 }, (_, index) => index + 1)
  }
  return FALLBACK_DURATIONS
}

export function normalizeVideoDuration(value: number, options: number[]): number {
  if (options.includes(value)) return value
  return options.reduce((closest, option) => (
    Math.abs(option - value) < Math.abs(closest - value) ? option : closest
  ))
}

export function formatVideoDurationOptions(options: number[]): string {
  const first = options[0]
  const last = options[options.length - 1]
  const consecutive = options.every((value, index) => index === 0 || value === options[index - 1] + 1)
  return consecutive && first !== last ? `${first}–${last} 秒` : `${options.join('、')} 秒`
}
