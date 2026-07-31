export type VideoGenerationMode = 'automatic' | 'custom'
export type VideoResultCount = 1 | 2 | 3 | 4
export type VideoActionIntensity = 'low' | 'standard' | 'high'
export type VideoCutMode = 'explicit_cuts' | 'continuous_when_possible'

export interface VideoComposerSettings {
  templateId: string
  siteProfileId: string
  generationMode: VideoGenerationMode
  customPrompt: string
  resultCount: VideoResultCount
  durationSeconds: number
  actionIntensity: VideoActionIntensity
  cutMode: VideoCutMode
}

type ComposerStorage = Pick<Storage, 'getItem' | 'setItem'>

const KEYS = {
  templateId: 'fixed-video-template',
  siteProfileId: 'fixed-site-profile',
  generationMode: 'fixed-generation-mode',
  customPrompt: 'fixed-custom-prompt',
  resultCount: 'fixed-result-count',
  durationSeconds: 'fixed-duration-seconds',
  actionIntensity: 'fixed-action-intensity',
  cutMode: 'fixed-cut-mode',
} as const

export function loadVideoComposerSettings(storage: Pick<ComposerStorage, 'getItem'>): VideoComposerSettings {
  const generationMode = storage.getItem(KEYS.generationMode)
  const resultCount = Number(storage.getItem(KEYS.resultCount))
  const durationSeconds = Number(storage.getItem(KEYS.durationSeconds))
  const actionIntensity = storage.getItem(KEYS.actionIntensity)
  const cutMode = storage.getItem(KEYS.cutMode)

  return {
    templateId: storage.getItem(KEYS.templateId) ?? '',
    siteProfileId: storage.getItem(KEYS.siteProfileId) ?? '',
    generationMode: generationMode === 'custom' ? 'custom' : 'automatic',
    customPrompt: storage.getItem(KEYS.customPrompt) ?? '',
    resultCount: resultCount === 2 || resultCount === 3 || resultCount === 4 ? resultCount : 1,
    durationSeconds: Number.isInteger(durationSeconds) && durationSeconds >= 3 && durationSeconds <= 15 ? durationSeconds : 10,
    actionIntensity: actionIntensity === 'low' || actionIntensity === 'high' ? actionIntensity : 'standard',
    cutMode: cutMode === 'continuous_when_possible' ? 'continuous_when_possible' : 'explicit_cuts',
  }
}

export function saveVideoComposerSettings(storage: Pick<ComposerStorage, 'setItem'>, settings: VideoComposerSettings): void {
  storage.setItem(KEYS.templateId, settings.templateId)
  storage.setItem(KEYS.siteProfileId, settings.siteProfileId)
  storage.setItem(KEYS.generationMode, settings.generationMode)
  storage.setItem(KEYS.customPrompt, settings.customPrompt)
  storage.setItem(KEYS.resultCount, String(settings.resultCount))
  storage.setItem(KEYS.durationSeconds, String(settings.durationSeconds))
  storage.setItem(KEYS.actionIntensity, settings.actionIntensity)
  storage.setItem(KEYS.cutMode, settings.cutMode)
}
