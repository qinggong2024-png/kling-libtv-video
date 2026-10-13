import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { DirectorTaskResponse } from './directorApi'
import { CreativePackageExportView } from './CreativePackageExportView'
import {
  copyCreativePackage,
  creativePackageDisplayText,
  creativePackageJson,
  creativePackageText,
  packageFieldText,
  selectCreativePackageExport,
  type CreativePackageDocument,
} from './creativePackageExport'

const document: CreativePackageDocument = {
  direction: { id: 'B', scene: 'indoor room', behavior: 'seated casually' },
  audience: null,
  characterDNA: null,
  sceneDNA: 'indoor room',
  cameraDNA: 'eye-level medium frame',
  imagePrompt: 'FAKE ONLY.\nPreserve exact garment SHA.',
  videoPrompt: null,
  shotPlan: [{ shot_id: 'FIRST_FRAME', package_id: 'first-package' }],
  qualityChecklist: [{ dimension: 'Camera', evidence: 'PROPOSED_FAKE' }],
  provenance: { schemaVersion: 'creative-package.v1', packageId: 'first-package', qualificationScope: 'OFFLINE_SYNTHETIC_ONLY', synthetic: true },
}

function workflow(exports: unknown = { 'first-package': document }): DirectorTaskResponse {
  return { creative_packages: exports } as unknown as DirectorTaskResponse
}

afterEach(() => vi.unstubAllGlobals())

describe('Creative Package export', () => {
  it('requires server export and an exact package mapping', () => {
    expect(selectCreativePackageExport(null, 'first-package')).toBeNull()
    expect(selectCreativePackageExport(workflow(), 'other-package')).toBeNull()
    expect(selectCreativePackageExport(workflow({ 'first-package': { direction: 'B' } }), 'first-package')).toBeNull()
    expect(selectCreativePackageExport(workflow({ 'first-package': { ...document, provenance: { schemaVersion: 'creative-package.v1', packageId: 'other-package' } } }), 'first-package')).toBeNull()
    expect(selectCreativePackageExport(workflow(), 'first-package')).toBe(document)
  })

  it('exports exact prompts, provenance and honest missing fields without mutation', () => {
    const before = structuredClone(document)
    const json = JSON.parse(creativePackageJson(document))
    expect(json).toEqual(document)
    expect(json.imagePrompt).toBe(document.imagePrompt)
    const text = creativePackageText(document)
    expect(text).toContain(document.imagePrompt)
    expect(text).toContain('OFFLINE_SYNTHETIC_ONLY')
    expect(text).toContain('未提供 · 待人工确认')
    expect(document).toEqual(before)
    expect(packageFieldText(null)).toBe('未提供 · 待人工确认')
  })

  it('offers no video copy when video Prompt is missing', () => {
    const markup = renderToStaticMarkup(<CreativePackageExportView workflow={workflow()} packageId="first-package" />)
    expect(markup).toContain('复制图片 Prompt')
    expect(markup).not.toContain('aria-label="复制视频 Prompt"')
    expect(markup).toContain('下载 Creative Package JSON')
    expect(markup).toContain('OFFLINE_SYNTHETIC_ONLY')
  })

  it('does not invent exports for historical snapshots', () => {
    const markup = renderToStaticMarkup(<CreativePackageExportView workflow={null} packageId="first-package" />)
    expect(markup).toContain('暂无可导出合同')
    expect(markup).not.toContain('<button')
  })

  it('keeps machine evidence out of the compact shot presentation', () => {
    const shot = { shotId: 'SHOT_01', packageId: 'shot-package', revision: 2, sourcePackage: { prompt: 'exact original prompt' } }
    expect(creativePackageDisplayText('shotPlan', [shot])).toBe('SHOT_01 · r2\nshot-package')
    expect(creativePackageDisplayText('sceneDNA', { description: 'bedroom', origin: 'PROPOSED' })).toBe('bedroom')
    expect(creativePackageDisplayText('imagePrompt', document.imagePrompt)).toBe(document.imagePrompt)
    expect(creativePackageJson({ ...document, shotPlan: [shot] })).toContain('exact original prompt')
  })

  it('awaits clipboard and propagates failure for visible feedback', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    await copyCreativePackage(document.imagePrompt as string)
    expect(writeText).toHaveBeenCalledExactlyOnceWith(document.imagePrompt)
    writeText.mockRejectedValue(new Error('denied'))
    await expect(copyCreativePackage('test')).rejects.toThrow('denied')
    vi.stubGlobal('navigator', {})
    await expect(copyCreativePackage('test')).rejects.toThrow('CLIPBOARD_UNAVAILABLE')
  })
})
