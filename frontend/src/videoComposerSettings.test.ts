import { describe, expect, it } from 'vitest'

import { loadVideoComposerSettings, saveVideoComposerSettings } from './videoComposerSettings'

function memoryStorage(initial: Record<string, string> = {}) {
  const values = new Map(Object.entries(initial))
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value) },
    values,
  }
}

describe('video composer settings', () => {
  it('restores prompts and every generation parameter independently from image state', () => {
    const storage = memoryStorage({
      'fixed-video-template': 'template-2',
      'fixed-site-profile': 'profile-3',
      'fixed-generation-mode': 'custom',
      'fixed-custom-prompt': '视频专用动作与镜头提示词',
      'fixed-result-count': '4',
      'fixed-duration-seconds': '12',
      'fixed-action-intensity': 'high',
      'fixed-cut-mode': 'continuous_when_possible',
    })

    expect(loadVideoComposerSettings(storage)).toEqual({
      templateId: 'template-2',
      siteProfileId: 'profile-3',
      generationMode: 'custom',
      customPrompt: '视频专用动作与镜头提示词',
      resultCount: 4,
      durationSeconds: 12,
      actionIntensity: 'high',
      cutMode: 'continuous_when_possible',
    })
  })

  it('uses safe defaults for missing or invalid stored values', () => {
    const storage = memoryStorage({
      'fixed-generation-mode': 'image',
      'fixed-result-count': '8',
      'fixed-action-intensity': 'extreme',
      'fixed-cut-mode': 'random',
    })

    expect(loadVideoComposerSettings(storage)).toMatchObject({
      generationMode: 'automatic',
      customPrompt: '',
      resultCount: 1,
      durationSeconds: 10,
      actionIntensity: 'standard',
      cutMode: 'explicit_cuts',
    })
  })

  it('persists the complete video form as one settings snapshot', () => {
    const storage = memoryStorage()
    saveVideoComposerSettings(storage, {
      templateId: 'template-1',
      siteProfileId: 'profile-1',
      generationMode: 'automatic',
      customPrompt: '保留的自定义视频提示词',
      resultCount: 3,
      durationSeconds: 15,
      actionIntensity: 'low',
      cutMode: 'explicit_cuts',
    })

    expect(Object.fromEntries(storage.values)).toEqual({
      'fixed-video-template': 'template-1',
      'fixed-site-profile': 'profile-1',
      'fixed-generation-mode': 'automatic',
      'fixed-custom-prompt': '保留的自定义视频提示词',
      'fixed-result-count': '3',
      'fixed-duration-seconds': '15',
      'fixed-action-intensity': 'low',
      'fixed-cut-mode': 'explicit_cuts',
    })
  })
})
