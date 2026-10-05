import { afterEach, describe, expect, it, vi } from 'vitest'
import { readAppLocation } from './useAppNavigation'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('records navigation state', () => {
  it('reads only supported filter and query values from the URL', () => {
    vi.stubGlobal('window', { location: { search: '?view=records&filter=failed&q=coat%20test' } })
    expect(readAppLocation()).toMatchObject({
      view: 'records',
      recordsFilter: 'failed',
      recordsQuery: 'coat test',
    })
  })

  it('falls back to all records for invalid filters', () => {
    vi.stubGlobal('window', { location: { search: '?view=records&filter=unknown&q=term' } })
    expect(readAppLocation()).toMatchObject({
      view: 'records',
      recordsFilter: 'all',
      recordsQuery: 'term',
    })
  })
})
