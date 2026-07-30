import { describe, expect, it } from 'vitest'

import { mapWithConcurrency } from './concurrency'

describe('mapWithConcurrency', () => {
  it('preserves result order while enforcing the concurrency limit', async () => {
    let active = 0
    let maximumActive = 0
    const results = await mapWithConcurrency([8, 1, 5, 2], 2, async (value) => {
      active += 1
      maximumActive = Math.max(maximumActive, active)
      await new Promise((resolve) => setTimeout(resolve, value))
      active -= 1
      return value * 10
    })

    expect(results).toEqual([80, 10, 50, 20])
    expect(maximumActive).toBe(2)
  })

  it('returns an empty result without starting workers', async () => {
    const mapper = () => Promise.resolve('unused')
    expect(await mapWithConcurrency([], 4, mapper)).toEqual([])
  })

  it('waits for every worker to settle before surfacing a failure', async () => {
    const events: string[] = []
    const pending = mapWithConcurrency([1, 2], 2, async (value) => {
      if (value === 1) throw new Error('upload failed')
      await new Promise((resolve) => setTimeout(resolve, 10))
      events.push('slow worker settled')
      return value
    })

    await expect(pending).rejects.toThrow('upload failed')
    expect(events).toEqual(['slow worker settled'])
  })
})
