import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, getAIQuota, setApiUserId } from './api'

describe('AI quota authenticated read', () => {
  beforeEach(() => {
    vi.stubGlobal('window', globalThis)
    vi.stubGlobal('fetch', vi.fn())
    setApiUserId('quota-user')
  })

  afterEach(() => {
    setApiUserId(null)
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('preserves dollar strings and optional fields through the shared session request', async () => {
    const quota = { currency: 'USD', available: '0.001', pending_max: '10.000', historical_unknown: '2.000' }
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify(quota)))
    expect(await getAIQuota()).toEqual(quota)
    const [path, init] = vi.mocked(fetch).mock.calls[0]
    expect(path).toBe('/api/v1/ai-usage/quota')
    expect(init?.credentials).toBe('include')
    expect(new Headers(init?.headers).get('X-User-Id')).toBe('quota-user')
    expect(init?.method).toBeUndefined()
    expect(init?.body).toBeUndefined()
  })

  it('keeps shared-session identity and surfaces the existing 401 ApiError', async () => {
    setApiUserId(null)
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({
      detail: { code: 'AUTH_REQUIRED', message: '请重新登录' },
    }), { status: 401 }))
    await expect(getAIQuota()).rejects.toMatchObject({
      name: 'ApiError', status: 401, code: 'AUTH_REQUIRED', message: '请重新登录',
    })
    expect(new Headers(vi.mocked(fetch).mock.calls[0][1]?.headers).has('X-User-Id')).toBe(false)
  })

  it('does not substitute a successful quota when price configuration fails', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({
      detail: { code: 'AI_PRICE_NOT_CONFIGURED', message: '价格未配置' },
    }), { status: 503 }))
    const error = await getAIQuota().catch((cause) => cause)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ code: 'AI_PRICE_NOT_CONFIGURED' })
  })

  it('passes caller cancellation into the shared request', async () => {
    const controller = new AbortController()
    vi.mocked(fetch).mockImplementation((_path, init) => new Promise((_resolve, reject) => {
      init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true })
    }))
    const request = getAIQuota(controller.signal)
    controller.abort()
    await expect(request).rejects.toMatchObject({ name: 'AbortError' })
    expect(vi.mocked(fetch).mock.calls[0][1]?.signal?.aborted).toBe(true)
  })
})
