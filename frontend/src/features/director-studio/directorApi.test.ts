import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { login, logout, setApiUserId, setCsrfCookieName } from '../../api'
import {
  createDirectorProduct,
  createDirectorTask,
  DirectorApiError,
  getDirectorTask,
  sendDirectorCommand,
} from './directorApi'

function jsonResponse(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('Director Studio offline API adapter', () => {
  beforeEach(() => {
    vi.stubGlobal('window', globalThis)
    vi.stubGlobal('fetch', vi.fn())
    setApiUserId('00000000-0000-0000-0000-000000000001')
    setCsrfCookieName('libtv_csrf')
  })

  afterEach(async () => {
    vi.mocked(fetch).mockResolvedValueOnce(new Response(null, { status: 204 }))
    await logout()
    setApiUserId(null)
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('shares the RC login token without extra identity requests or a development user header', async () => {
    setApiUserId(null)
    setCsrfCookieName('libtv_rc_csrf')
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse({ csrfToken: 'rc-csrf' }))
      .mockResolvedValueOnce(jsonResponse({ id: 'product-1' }, 201))
    await login('rc-test', 'test-password-only')
    await createDirectorProduct('shared-context')
    expect(vi.mocked(fetch).mock.calls).toHaveLength(2)
    const call = vi.mocked(fetch).mock.calls[1]
    expect(new Headers(call[1]?.headers).get('X-CSRF-Token')).toBe('rc-csrf')
    expect(new Headers(call[1]?.headers).has('X-User-Id')).toBe(false)
    expect(call[1]?.credentials).toBe('include')
  })

  it('keeps validation reasons from the shared API contract', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({
      detail: [{ loc: ['body', 'internalSkuId'], msg: 'SKU is required' }],
    }, 422))
    await expect(createDirectorProduct('bad')).rejects.toMatchObject({
      code: 'VALIDATION_FAILED', status: 422, message: 'internalSkuId: SKU is required',
    })
  })

  it('uses retry_analysis with the existing workflow identity and version', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ id: 'existing', status: 'AWAITING_DIRECTION' }))
    await sendDirectorCommand('existing', {
      action: 'retry_analysis', expected_version: 3, command_key: 'same-retry',
    })
    expect(String(vi.mocked(fetch).mock.calls[0][0])).toBe('/api/v1/creative-workflow/tasks/existing/commands')
    expect(JSON.parse(String(vi.mocked(fetch).mock.calls[0][1]?.body))).toEqual({
      action: 'retry_analysis', expected_version: 3, command_key: 'same-retry',
    })
  })

  it('creates a product using the existing authenticated context without changing api.ts', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ id: 'product-1' }, 201))

    await createDirectorProduct('director-jacket-1')

    const call = vi.mocked(fetch).mock.calls[0]
    expect(String(call[0])).toBe('/api/v1/products')
    expect(new Headers(call[1]?.headers).get('X-User-Id')).toBe('00000000-0000-0000-0000-000000000001')
    expect(JSON.parse(String(call[1]?.body))).toEqual({ internalSkuId: 'director-jacket-1' })
  })

  it('uploads one front image and sends the offline command sequence fields', async () => {
    const file = new File(['front'], 'front.png', { type: 'image/png' })
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse({ id: 'task-1', status: 'DRAFT', state_version: 0, snapshot: {}, mode: 'OFFLINE_FAKE_ONLY' }, 201))
      .mockResolvedValueOnce(jsonResponse({ id: 'task-1', status: 'AWAITING_DIRECTION', state_version: 1, snapshot: {}, mode: 'OFFLINE_FAKE_ONLY' }))

    await createDirectorTask({ productId: 'product-1', front: file, clientKey: 'director-client-1' })
    await sendDirectorCommand('task-1', {
      action: 'analyze',
      expected_version: 0,
      command_key: 'analyze-1',
    })

    const taskCall = vi.mocked(fetch).mock.calls[0]
    const form = taskCall[1]?.body as FormData
    expect(String(taskCall[0])).toBe('/api/v1/creative-workflow/tasks')
    expect(form.get('product_id')).toBe('product-1')
    expect(form.get('client_key')).toBe('director-client-1')
    expect((form.get('front') as File).name).toBe('front.png')
    expect(JSON.parse(String(vi.mocked(fetch).mock.calls[1][1]?.body))).toMatchObject({
      action: 'analyze',
      command_key: 'analyze-1',
      expected_version: 0,
    })
  })

  it('keeps structured offline errors visible to the page', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({
      detail: { code: 'OFFLINE_WORKFLOW_DISABLED', message: 'offline only' },
    }, 403))

    await expect(createDirectorProduct('director-jacket-1')).rejects.toMatchObject({
      status: 403,
      code: 'OFFLINE_WORKFLOW_DISABLED',
      message: 'offline only',
    } satisfies Partial<DirectorApiError>)
  })

  it('sends separate review and selection commands with candidate, reason and version evidence', async () => {
    vi.mocked(fetch).mockImplementation(async () => jsonResponse({ id: 'task-1' }))
    await sendDirectorCommand('task-1', {
      action: 'review', expected_version: 4, command_key: 'reject-1',
      candidate_id: 'candidate-1', decision: 'REJECTED', reason: '商品印花不一致',
    })
    await sendDirectorCommand('task-1', {
      action: 'review', expected_version: 5, command_key: 'approve-1',
      candidate_id: 'candidate-1', decision: 'QUALIFIED',
    })
    await sendDirectorCommand('task-1', {
      action: 'select', expected_version: 6, command_key: 'select-1',
      candidate_id: 'candidate-1',
    })
    expect(vi.mocked(fetch).mock.calls.map((call) => JSON.parse(String(call[1]?.body)))).toEqual([
      { action: 'review', expected_version: 4, command_key: 'reject-1', candidate_id: 'candidate-1', decision: 'REJECTED', reason: '商品印花不一致' },
      { action: 'review', expected_version: 5, command_key: 'approve-1', candidate_id: 'candidate-1', decision: 'QUALIFIED' },
      { action: 'select', expected_version: 6, command_key: 'select-1', candidate_id: 'candidate-1' },
    ])
  })

  it('sends storyboard scope and shot identity without changing the command endpoint', async () => {
    vi.mocked(fetch).mockImplementation(async () => jsonResponse({ id: 'task-1' }))
    await sendDirectorCommand('task-1', {
      action: 'authorize',
      expected_version: 7,
      command_key: 'storyboard-authorize-1',
      authorization: {
        authorization_id: 'auth-storyboard-1',
        package_id: 'task-1:storyboard:SHOT_01:1',
        locks_hash: 'locks',
        scope: 'VIDEO_STORYBOARD',
        shot_ids: ['SHOT_01'],
        expires_at: '2026-10-12T02:00:00.000Z',
        loop_enabled: false,
        max_revisions: 0,
        max_calls: 6,
        max_cost_micros: 6,
        currency: 'FAKE',
        allowed_modules: ['Reality'],
      },
    })
    await sendDirectorCommand('task-1', {
      action: 'select',
      expected_version: 8,
      command_key: 'storyboard-select-1',
      candidate_id: 'storyboard-candidate-1',
      shot_id: 'SHOT_01',
    })

    expect(vi.mocked(fetch).mock.calls.map((call) => JSON.parse(String(call[1]?.body)))).toEqual([
      expect.objectContaining({
        action: 'authorize',
        authorization: expect.objectContaining({
          scope: 'VIDEO_STORYBOARD',
          shot_ids: ['SHOT_01'],
        }),
      }),
      expect.objectContaining({
        action: 'select',
        candidate_id: 'storyboard-candidate-1',
        shot_id: 'SHOT_01',
      }),
    ])
  })

  it('reads current task state without submitting a command', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({
      id: 'task-1', state_version: 7,
      snapshot: {
        latest_review: {
          candidate_id: 'candidate-1',
          reviewer_id: 'reviewer-1',
          decision: 'REJECTED',
          qualification_scope: 'OFFLINE_SYNTHETIC_ONLY',
          reason: '印花与原商品不一致',
        },
      },
    }))
    expect(await getDirectorTask('task-1')).toMatchObject({
      state_version: 7,
      snapshot: { latest_review: { candidate_id: 'candidate-1', decision: 'REJECTED', reason: '印花与原商品不一致' } },
    })
    expect(String(vi.mocked(fetch).mock.calls[0][0])).toBe('/api/v1/creative-workflow/tasks/task-1')
    expect(vi.mocked(fetch).mock.calls[0][1]?.body).toBeUndefined()
  })
})
