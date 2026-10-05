import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { FoundationConfirmPanel, FoundationDrawer, FoundationThumbnail } from './ui'

describe('UI foundations', () => {
  it('gives confirmation panels unique accessible titles', () => {
    const markup = renderToStaticMarkup(<><FoundationConfirmPanel title="First" onConfirm={() => {}} /><FoundationConfirmPanel title="Second" onConfirm={() => {}} /></>)
    const ids = [...markup.matchAll(/aria-labelledby="([^"]+)"/g)].map((match) => match[1])
    expect(ids).toHaveLength(2)
    expect(new Set(ids).size).toBe(2)
    ids.forEach((id) => expect(markup).toContain(`id="${id}"`))
  })

  it('uses a native modal container and unmounts closed drawers', () => {
    expect(renderToStaticMarkup(<FoundationDrawer open={false} title="Details" onClose={() => {}}>Content</FoundationDrawer>)).toBe('')
    const markup = renderToStaticMarkup(<FoundationDrawer open title="Details" onClose={() => {}}>Content</FoundationDrawer>)
    expect(markup).toContain('<dialog')
    expect(markup).toContain('aria-labelledby=')
  })

  it('preserves the full review image by default', () => {
    const markup = renderToStaticMarkup(<FoundationThumbnail src="/synthetic.png" alt="Review" ratio="portrait" />)
    expect(markup).toContain('foundation-thumbnail--portrait')
    expect(markup).toContain('foundation-thumbnail--contain')
    expect(markup).toContain('alt="Review"')
  })
})
