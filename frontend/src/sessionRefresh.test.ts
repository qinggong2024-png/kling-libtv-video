import { describe, expect, it } from 'vitest'
import { ApiError } from './api'
import { settleSessionRefresh } from './sessionRefresh'

describe('session refresh authentication precedence', () => {
  const unauthorized = () => new ApiError(401, 'AUTH_REQUIRED', 'Login required')
  const unavailable = () => new ApiError(500, 'UNAVAILABLE', 'Unavailable')

  it.each(['page', 'actor'] as const)('rejects %s 401 instead of exposing fulfilled partial data', async (side) => {
    const error = unauthorized()
    await expect(settleSessionRefresh(
      side === 'page' ? Promise.reject(error) : Promise.resolve({ items: ['private task'] }),
      side === 'actor' ? Promise.reject(error) : Promise.resolve({ id: 'old-user' }),
    )).rejects.toBe(error)
  })

  it.each(['page', 'actor'] as const)('prioritizes %s 401 over the other request 500', async (side) => {
    const error = unauthorized()
    await expect(settleSessionRefresh(
      Promise.reject(side === 'page' ? error : unavailable()),
      Promise.reject(side === 'actor' ? error : unavailable()),
    )).rejects.toBe(error)
  })

  it('preserves partial refresh on non-authentication errors', async () => {
    const error = unavailable()
    expect(await settleSessionRefresh(Promise.reject(error), Promise.resolve({ id: 'user' }))).toEqual([
      { status: 'rejected', reason: error },
      { status: 'fulfilled', value: { id: 'user' } },
    ])
  })

  it('returns both successful results', async () => {
    expect(await settleSessionRefresh(Promise.resolve({ items: [] }), Promise.resolve({ id: 'user' }))).toEqual([
      { status: 'fulfilled', value: { items: [] } },
      { status: 'fulfilled', value: { id: 'user' } },
    ])
  })
})
