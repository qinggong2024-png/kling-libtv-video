import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getCurrentUser, getSystemStatus } from '../../api'
import {
  createDirectorProduct,
  createDirectorTask,
  DirectorApiError,
  getDirectorTask,
  sendDirectorCommand,
} from './directorApi'

vi.mock('../../api', () => ({
  getCurrentUser: vi.fn(),
  getSystemStatus: vi.fn(),
}))

function jsonResponse(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const system = {
  sharedAuthentication: false,
  csrfCookieName: 'libtv_csrf',
} as Awaited<ReturnType<typeof getSystemStatus>>

describe('Director Studio offline API adapter', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    vi.mocked(getSystemStatus).mockResolvedValue(system)
    vi.mocked(getCurrentUser).mockResolvedValue({
      userId: '00000000-0000-0000-0000-000000000001',
      username: 'phase-one-user',
      role: 'USER',
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
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
