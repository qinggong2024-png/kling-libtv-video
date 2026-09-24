import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { ImageOutputReview, OutputCard } from './ImageCenter'
import type { ImageGenerationOutput } from './imageCenterModel'

const output: ImageGenerationOutput = {
  id: 'output-1', kind: 'fusion', view: 'front', label: '正面结果',
  file: null, url: '', qualificationStatus: 'PENDING',
}

describe('image review controls', () => {
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
})
