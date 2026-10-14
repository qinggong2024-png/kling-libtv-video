import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { ContentLibraryView } from './ContentLibraryView'

describe('ContentLibraryView accessibility contract', () => {
  it('renders labelled tab panels and a keyboard-focusable active tab', () => {
    const markup = renderToStaticMarkup(<ContentLibraryView actorId={null} canDeleteSubjects={false} canEditCatalog={false} />)

    expect(markup).toContain('role="tablist" aria-label="内容库归属"')
    expect(markup).toContain('id="general-tab"')
    expect(markup).toContain('aria-controls="general-panel"')
    expect(markup).toContain('id="general-panel" role="tabpanel" aria-labelledby="general-tab"')
    expect(markup).toContain('id="actions-tab"')
    expect(markup).toContain('aria-controls="actions-panel"')
    expect(markup).toContain('id="actions-panel" role="tabpanel" aria-labelledby="actions-tab"')
    expect(markup).toContain('tabindex="0"')
    expect(markup).toContain('tabindex="-1"')
  })

  it('labels the embedded maintenance surface as the brand asset library', () => {
    const markup = renderToStaticMarkup(<ContentLibraryView embedded actorId={null} canDeleteSubjects={false} canEditCatalog={false} />)

    expect(markup).toContain('低频维护配置')
    expect(markup).toContain('品牌资产库')
    expect(markup).toContain('三个生产工作区会从这里调用可用资产')
    expect(markup).toContain('class="settings-section content-library-view content-library-view--embedded"')
  })
})
