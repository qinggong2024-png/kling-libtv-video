import { describe, expect, it, vi } from 'vitest'
import { collectHistory } from './historyPagination'

describe('history pagination', () => {
  it('reads beyond the first 100 records', async () => {
    const read = vi.fn().mockResolvedValueOnce({ items: Array.from({ length: 100 }, (_, id) => id), nextCursor: 'page-2' })
      .mockResolvedValueOnce({ items: [100], nextCursor: null })
    expect(await collectHistory(read)).toHaveLength(101)
    expect(read.mock.calls[1][0]).toBe('page-2')
  })
  it('rejects repeated cursors without returning a truncated successful history', async () => {
    const read = vi.fn().mockResolvedValue({ items: [1], nextCursor: 'same' })
    await expect(collectHistory(read)).rejects.toThrow('历史分页异常')
    expect(read).toHaveBeenCalledTimes(2)
  })
  it('rejects an empty page claiming more results', async () => {
    await expect(collectHistory(async () => ({ items: [], nextCursor: 'next' }))).rejects.toThrow()
  })
  it('does not start another page after cancellation', async () => {
    const controller = new AbortController()
    const read = vi.fn(async () => {
      controller.abort()
      return { items: [1], nextCursor: 'next' }
    })
    await expect(collectHistory(read, controller.signal)).rejects.toMatchObject({ name: 'AbortError' })
    expect(read).toHaveBeenCalledTimes(1)
  })
})
