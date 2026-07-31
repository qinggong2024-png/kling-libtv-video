import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

import { SubjectInputPanel } from './SubjectInputPanel'
import { createEmptySubjectReferenceFiles } from './subjectFiles'
import { fillSubjectDropSlots, isSubjectPanelDropExcluded } from './subjectPanelDrop'

const baseProps = {
  onModeChange: vi.fn(),
  uploadedFiles: createEmptySubjectReferenceFiles(),
  onUploadedFilesChange: vi.fn(),
  selectedElementId: '',
  onSelectedElementIdChange: vi.fn(),
  storyboardReferenceCount: 5,
}

describe('SubjectInputPanel', () => {
  it('fills empty subject slots in visual order for a panel-level drop', () => {
    const [front, back, side, detail] = ['front.png', 'back.png', 'side.png', 'detail.png']
      .map((name) => new File([name], name, { type: 'image/png' }))

    const result = fillSubjectDropSlots(createEmptySubjectReferenceFiles(), [front, back, side, detail])

    expect(result.acceptedCount).toBe(4)
    expect(result.files).toEqual({
      frontalImage: front,
      backImage: back,
      detailImages: [side, detail],
    })
  })

  it('preserves filled slots and rejects panel-level drop overflow', () => {
    const existingFront = new File(['front'], 'existing-front.png', { type: 'image/png' })
    const existingSide = new File(['side'], 'existing-side.png', { type: 'image/png' })
    const [back, detail, overflow] = ['back.png', 'detail.png', 'overflow.png']
      .map((name) => new File([name], name, { type: 'image/png' }))

    const result = fillSubjectDropSlots({
      frontalImage: existingFront,
      backImage: null,
      detailImages: [existingSide],
    }, [back, detail, overflow])

    expect(result.acceptedCount).toBe(2)
    expect(result.files).toEqual({
      frontalImage: existingFront,
      backImage: back,
      detailImages: [existingSide, detail],
    })
  })

  it('excludes nested controls and upload tiles from the panel-level drop target', () => {
    const closest = vi.fn().mockReturnValue({})
    const nestedControl = {
      closest,
    } as unknown as EventTarget
    const panelWhitespace = {
      closest: vi.fn().mockReturnValue(null),
    } as unknown as EventTarget

    expect(isSubjectPanelDropExcluded(nestedControl)).toBe(true)
    expect(closest).toHaveBeenCalledWith(expect.stringContaining('button'))
    expect(closest).toHaveBeenCalledWith(expect.stringContaining('.subject-upload-tile'))
    expect(isSubjectPanelDropExcluded(panelWhitespace)).toBe(false)
    expect(isSubjectPanelDropExcluded(null)).toBe(false)
  })

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

  it('renders local thumbnail containers for uploaded subject images', () => {
    const front = new File(['front'], 'front.png', { type: 'image/png' })
    const side = new File(['side'], 'side.png', { type: 'image/png' })
    const markup = renderToStaticMarkup(<SubjectInputPanel
      {...baseProps}
      mode="upload"
      uploadedFiles={{
        frontalImage: front,
        backImage: null,
        detailImages: [side],
      }}
      elements={[]}
    />)
    expect(markup).toContain('subject-upload-tile__preview')
    expect(markup).toContain('正面图预览：front.png')
    expect(markup).toContain('侧面图预览：side.png')
    expect(markup).not.toContain('点击更换')
  })

  it('marks uploaded subject media for desktop alignment when storyboards are present', () => {
    const front = new File(['front'], 'front.png', { type: 'image/png' })
    const alignedMarkup = renderToStaticMarkup(<SubjectInputPanel
      {...baseProps}
      mode="upload"
      uploadedFiles={{
        frontalImage: front,
        backImage: null,
        detailImages: [],
      }}
      elements={[]}
    />)
    const subjectOnlyMarkup = renderToStaticMarkup(<SubjectInputPanel
      {...baseProps}
      mode="upload"
      uploadedFiles={{
        frontalImage: front,
        backImage: null,
        detailImages: [],
      }}
      storyboardReferenceCount={0}
      elements={[]}
    />)
    const historyMarkup = renderToStaticMarkup(<SubjectInputPanel
      {...baseProps}
      mode="history"
      uploadedFiles={{
        frontalImage: front,
        backImage: null,
        detailImages: [],
      }}
      elements={[]}
    />)

    expect(alignedMarkup).toContain('subject-input-panel--align-uploaded-media')
    expect(subjectOnlyMarkup).not.toContain('subject-input-panel--align-uploaded-media')
    expect(historyMarkup).not.toContain('subject-input-panel--align-uploaded-media')
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
