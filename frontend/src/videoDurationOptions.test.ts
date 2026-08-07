import { describe, expect, it } from 'vitest'

import type { VideoGenerationStatus } from './types'
import {
  formatVideoDurationOptions,
  getVideoDurationOptions,
  normalizeVideoDuration,
} from './videoDurationOptions'

function status(overrides: Partial<VideoGenerationStatus> = {}): VideoGenerationStatus {
  return {
    enabled: true,
    backend: 'api',
    provider: 'kling_official_api',
    status: 'available',
    available: true,
    authenticated: true,
    reason: null,
    cliVersion: 'api-v1',
    models: ['model'],
    supportsMultipleImages: true,
    imageInputLimit: 7,
    videoDurations: ['3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13', '14', '15'],
    tailImageVideoDurations: ['3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13', '14', '15'],
    fallbackMode: 'first_last_frame',
    ...overrides,
  }
}

describe('video duration options', () => {
  it('uses provider-advertised durations for a single image', () => {
    expect(getVideoDurationOptions(status({ videoDurations: ['8', '4', '6', '6'] }), 1))
      .toEqual([4, 6, 8])
  })

  it('uses the tail-image contract when a second storyboard is present', () => {
    const bach = status({
      backend: 'bach',
      provider: 'bach',
      videoDurations: ['1', '2', '3', '4', '5', '6', '7', '8'],
      tailImageVideoDurations: ['1', '2', '3', '4', '5', '6'],
    })

    expect(getVideoDurationOptions(bach, 1)).toEqual([1, 2, 3, 4, 5, 6, 7, 8])
    expect(getVideoDurationOptions(bach, 2)).toEqual([1, 2, 3, 4, 5, 6])
    expect(normalizeVideoDuration(8, getVideoDurationOptions(bach, 2))).toBe(6)
  })

  it('keeps safe Bach limits while an older backend is rolling forward', () => {
    const bach = status({ backend: 'bach', videoDurations: [], tailImageVideoDurations: [] })

    expect(getVideoDurationOptions(bach, 1)).toEqual([1, 2, 3, 4, 5, 6, 7, 8])
    expect(getVideoDurationOptions(bach, 2)).toEqual([1, 2, 3, 4, 5, 6])
  })

  it('formats contiguous and discrete duration choices', () => {
    expect(formatVideoDurationOptions([1, 2, 3, 4, 5, 6])).toBe('1–6 秒')
    expect(formatVideoDurationOptions([4, 6, 8])).toBe('4、6、8 秒')
  })
})
