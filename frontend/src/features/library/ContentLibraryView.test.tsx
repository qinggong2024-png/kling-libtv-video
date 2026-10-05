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
})
