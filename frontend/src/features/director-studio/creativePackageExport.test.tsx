import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { DirectorTaskResponse } from './directorApi'
import { CreativePackageExportView } from './CreativePackageExportView'
import {
  copyCreativePackage,
  creativePackageDisplayText,
  creativePackageFieldSource,
  creativePackageFieldStatus,
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
    expect(markup).toContain('复制图片生成提示词全文')
    expect(markup).not.toContain('aria-label="复制视频创作提案全文"')
    expect(markup).toContain('下载 Creative Package JSON')
    expect(markup).toContain('Fake · 离线合成 · 不可交付')
  })

  it('separates handoff content and collapsed technical evidence without altering the contract', () => {
    const before = structuredClone(document)
    const markup = renderToStaticMarkup(<CreativePackageExportView workflow={workflow()} packageId="first-package"><p>Bridge evidence</p></CreativePackageExportView>)
    const technical = markup.indexOf('<summary>技术详情</summary>')
    for (const label of ['制作要求', '图片生成提示词', '视频创作提案', '镜头规划', '质量检查']) {
      expect(markup.indexOf(`<h3>${label}</h3>`)).toBeLessThan(technical)
    }
    expect(markup).not.toContain('<details class="creative-package-technical" open')
    expect(markup.indexOf('Bridge evidence')).toBeGreaterThan(technical)
    expect(markup).toContain('不代表已完成分镜')
    expect(markup).toContain('规划内容不等于已验证生产内容')
    expect(document).toEqual(before)
  })

  it('keeps technical workflow available for a historical package without inventing an export', () => {
    const markup = renderToStaticMarkup(<CreativePackageExportView workflow={null} packageId="first-package"><p>Existing Fake workflow</p></CreativePackageExportView>)
    expect(markup).toContain('暂无可导出合同')
    expect(markup).toContain('Existing Fake workflow')
    expect(markup).not.toContain('<button')
  })

  it('labels only provided field statuses and origins, never grants execution qualification', () => {
    const proposed = { ...document, videoPrompt: 'FAKE SOURCE. Complete proposal.',
      fieldStatus: { imagePrompt: 'PRESENT', videoPrompt: 'PROPOSED' },
      provenance: { ...document.provenance as object, originEvidence: { fieldSources: {
        imagePrompt: 'package.prompt',
        videoPrompt: 'proposed-video-handoff.v1(plan.directions[selected_direction])',
        audience: 'plan.brand_dna.audience',
      } } },
    }
    expect(creativePackageFieldSource(proposed, 'imagePrompt')).toBe('冻结生产包原文')
    expect(creativePackageFieldSource(proposed, 'videoPrompt')).toContain('交接提案')
    expect(creativePackageFieldSource(proposed, 'audience')).toBe('任务绑定的品牌上下文')
    expect(creativePackageFieldStatus(proposed, 'videoPrompt')).toBe('创意提案 · 待人工确认')
    expect(creativePackageFieldStatus(proposed, 'imagePrompt')).toBe('已记录 · 未验证生产内容')
    expect(creativePackageFieldStatus(proposed, 'audience')).toBe('未提供')
    expect(creativePackageFieldSource(document, 'cameraDNA')).toBe('未提供')
    expect(creativePackageFieldStatus(document, 'cameraDNA')).toBe('状态未提供')
    const markup = renderToStaticMarkup(<CreativePackageExportView workflow={workflow({ 'first-package': proposed })} packageId="first-package" />)
    expect(markup).not.toMatch(/生产就绪|可执行|已完成<\/|质检通过<\/|<textarea/)
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
