import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

import { SubjectInputPanel } from './SubjectInputPanel'
import { createEmptySubjectReferenceFiles } from './subjectFiles'

const baseProps = {
  onModeChange: vi.fn(),
  uploadedFiles: createEmptySubjectReferenceFiles(),
  onUploadedFilesChange: vi.fn(),
  selectedElementId: '',
  onSelectedElementIdChange: vi.fn(),
  storyboardReferenceCount: 5,
}

describe('SubjectInputPanel', () => {
  it('shows the three subject upload areas by default', () => {
    const markup = renderToStaticMarkup(<SubjectInputPanel
      {...baseProps}
      mode="none"
      elements={[]}
    />)
    expect(markup).toContain('一致性主体')
    expect(markup).not.toContain('留空也可直接生成')
    expect(markup).not.toContain('上传新主体')
    expect(markup).toContain('历史主体')
    expect(markup).not.toContain('>不使用<')
    expect(markup).not.toContain('清除主体')
    expect(markup).toContain('subject-upload-grid')
    expect(markup).toContain('正面图')
    expect(markup).toContain('背面图')
    expect(markup).toContain('侧面图')
    expect(markup).toContain('拖拽或选择')
    expect(markup).not.toContain('5/7')
    expect(markup).not.toContain('未使用主体')
  })

  it('renders three compact upload tiles without exposing provider field names', () => {
    const markup = renderToStaticMarkup(<SubjectInputPanel
      {...baseProps}
      mode="upload"
      elements={[]}
    />)
    expect(markup).toContain('subject-upload-grid')
    expect(markup.match(/subject-upload-tile/g)?.length).toBeGreaterThanOrEqual(3)
    expect(markup).toContain('正面图')
    expect(markup).toContain('背面图')
    expect(markup).toContain('侧面图')
    expect(markup).not.toContain('frontal_image')
    expect(markup).not.toContain('refer_image')
    expect(markup).toContain('清除主体')
  })

  it('renders usable history elements as thumbnail cards and hides unavailable entries', () => {
    const markup = renderToStaticMarkup(<SubjectInputPanel
      {...baseProps}
      mode="history"
      elements={[
        {
          id: 'ready-1',
          name: '黑色印花上衣',
          description: '正背面参考',
          status: 'active',
          imageUrls: ['front.jpg', 'back.jpg'],
        },
        {
          id: 'pending-1',
          name: '处理中主体',
          description: null,
          status: 'processing',
          imageUrls: [],
        },
      ]}
      selectedElementId="ready-1"
      elementsError="历史主体暂时无法刷新"
    />)
    expect(markup).toContain('subject-history-grid')
    expect(markup).toContain('subject-history-card is-selected')
    expect(markup).toContain('aria-pressed="true"')
    expect(markup).toContain('黑色印花上衣')
    expect(markup).not.toContain('处理中主体')
    expect(markup).not.toContain('<select')
    expect(markup).toContain('历史主体暂时无法刷新')
    expect(markup).not.toContain('6/7')
  })

  it('collapses history after six cards and exposes a more control', () => {
    const elements = Array.from({ length: 8 }, (_, index) => ({
      id: `ready-${index + 1}`,
      name: `主体 ${index + 1}`,
      description: null,
      status: 'active',
      imageUrls: [`subject-${index + 1}.jpg`],
    }))
    const markup = renderToStaticMarkup(<SubjectInputPanel
      {...baseProps}
      mode="history"
      elements={elements}
    />)
    expect(markup).toContain('主体 6')
    expect(markup).not.toContain('主体 7')
    expect(markup).toContain('查看更多（2）')
    expect(markup).toContain('aria-expanded="false"')
  })

  it.each(['succeed', 'ready', 'success', 'succeeded', 'completed', 'active'])(
    'allows a history element with the %s status',
    (status) => {
      const markup = renderToStaticMarkup(<SubjectInputPanel
        {...baseProps}
        mode="history"
        elements={[{
          id: `element-${status}`,
          name: `主体 ${status}`,
          description: null,
          status,
          imageUrls: [],
        }]}
        selectedElementId={`element-${status}`}
      />)
      expect(markup).toContain(`主体 ${status}`)
      expect(markup).toContain('aria-pressed="true"')
      expect(markup).not.toContain('暂不能用于生成')
    },
  )

  it('does not present a local placeholder job as a selectable history card', () => {
    const markup = renderToStaticMarkup(<SubjectInputPanel
      {...baseProps}
      mode="history"
      elements={[{
        id: 'local-job:123',
        name: '正在创建的主体',
        description: null,
        status: 'succeed',
        imageUrls: [],
        raw: { localJob: true },
      }]}
      selectedElementId="local-job:123"
    />)
    expect(markup).not.toContain('subject-history-card')
    expect(markup).toContain('暂无可用历史主体')
    expect(markup).toContain('暂不能用于生成')
  })

  it('keeps loading and empty history states accessible', () => {
    const loadingMarkup = renderToStaticMarkup(<SubjectInputPanel
      {...baseProps}
      mode="history"
      elements={[]}
      elementsLoading
    />)
    expect(loadingMarkup).toContain('role="status"')
    expect(loadingMarkup).toContain('正在加载历史主体')

    const emptyMarkup = renderToStaticMarkup(<SubjectInputPanel
      {...baseProps}
      mode="history"
      elements={[]}
    />)
    expect(emptyMarkup).toContain('暂无可用历史主体')
  })
})
