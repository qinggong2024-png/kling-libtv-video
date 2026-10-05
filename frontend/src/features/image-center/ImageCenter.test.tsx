import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { BatchImageOutputReview, ImageOutputReview, OutputCard } from './ImageCenter'
import type { ImageGenerationOutput } from '../../imageCenterModel'

const output: ImageGenerationOutput = {
  id: 'output-1', kind: 'fusion', view: 'front', label: '正面结果',
  file: null, url: '', qualificationStatus: 'PENDING',
}

describe('image review controls', () => {
  const pendingOutput = (id: string): ImageGenerationOutput => ({
    ...output,
    id,
    label: `结果 ${id}`,
    qualificationStatus: 'PENDING',
  })

  it('shows independent selection and review controls without implying selection is approval', () => {
    const markup = renderToStaticMarkup(<OutputCard taskId="task-1" output={output} selected onToggle={() => {}} onReject={() => {}} onPreview={() => {}} />)
    expect(markup).toContain('aria-label="取消勾选正面结果"')
    expect(markup).toContain('aria-label="审核正面结果"')
    expect(markup).toContain('待人工审核')
    expect(markup).not.toContain('已合格')
  })

  it('requires explicit quality checks before saving and provides a reason field', () => {
    const markup = renderToStaticMarkup(<ImageOutputReview output={output} onSaved={() => {}} onClose={() => {}} />)
    expect(markup).toContain('<dialog')
    expect(markup.match(/type="checkbox"/g)).toHaveLength(2)
    expect(markup).not.toMatch(/type="checkbox"[^>]*checked/)
    expect(markup).toContain('class="primary-button" disabled=""')
    expect(markup).toContain('id="image-review-notes"')
    expect(markup).toContain('退回')
  })

  it('starts a batch review with one pending output and advances one item at a time', () => {
    const markup = renderToStaticMarkup(<BatchImageOutputReview outputs={[pendingOutput('output-1'), pendingOutput('output-2')]} onSaved={() => {}} onClose={() => {}} />)
    expect(markup).toContain('批量审核 · 1/2')
    expect(markup).toContain('完成当前项后自动进入下一张')
    expect(markup).toContain('审核备注')
    expect(markup).toContain('保存并继续')
    expect(markup).not.toContain('结果 output-2')
  })
})
