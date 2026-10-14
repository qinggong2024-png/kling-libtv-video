import { afterEach, describe, expect, it, vi } from 'vitest'
import { startHistoryPolling } from './useGeneratedHistory'

afterEach(() => vi.useRealTimers())

describe('isolated history polling', () => {
  it('waits for completion before scheduling another read', async () => {
    vi.useFakeTimers()
    let resolve!: (items: number[]) => void
    const read = vi.fn(() => new Promise<number[]>((done) => { resolve = done }))
    const publish = vi.fn()
    const stop = startHistoryPolling(read, publish)
    await Promise.resolve()
    await vi.advanceTimersByTimeAsync(90_000)
    expect(read).toHaveBeenCalledTimes(1)
    resolve([1])
    await Promise.resolve()
    await vi.advanceTimersByTimeAsync(29_999)
    expect(read).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1)
    expect(read).toHaveBeenCalledTimes(2)
    stop()
  })
  it('aborts old-owner reads and ignores their late results', async () => {
    let resolve!: (items: string[]) => void
    let signal!: AbortSignal
    const publish = vi.fn()
    const stop = startHistoryPolling((input) => {
      signal = input
      return new Promise<string[]>((done) => { resolve = done })
    }, publish)
    await Promise.resolve()
    stop()
    resolve(['previous-owner'])
    await Promise.resolve()
    expect(signal.aborted).toBe(true)
    expect(publish).toHaveBeenCalledTimes(1)
    expect(publish.mock.calls[0][0].items).toBeUndefined()
  })
  it('publishes source errors and retries without replacing retained items', async () => {
    vi.useFakeTimers()
    const publish = vi.fn()
    const read = vi.fn().mockRejectedValueOnce(new Error('forbidden')).mockResolvedValueOnce([2])
    const stop = startHistoryPolling(read, publish)
    await vi.advanceTimersByTimeAsync(0)
    expect(publish).toHaveBeenLastCalledWith({ loading: false, error: 'forbidden' })
    await vi.advanceTimersByTimeAsync(30_000)
    expect(publish).toHaveBeenLastCalledWith(expect.objectContaining({ items: [2], error: null }))
    stop()
  })
})
