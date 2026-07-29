import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cancelTask, confirmTask, createAdminUser, createTask, deactivateAdminUser, getAdminUsers, getLibTVAccountStatus, getOperations, getTaskPage, getTasks, login, loginKling, logoutKling, resetAdminUserPassword, runPromptAssistant, saveTaskPrompts, setApiUserId, setPromptAutoConfirmation, setVariantFeedback, startLibTVLogin, switchLibTVAccount } from './api'
import type { Task, UploadResult } from './types'

const USER_ID = '00000000-0000-0000-0000-000000000001'
const ADMIN_ID = '00000000-0000-0000-0000-000000000099'

function jsonResponse(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('API request identity and CSRF contracts', () => {
  beforeEach(() => {
    vi.stubGlobal('window', globalThis)
    vi.stubGlobal('fetch', vi.fn())
    setApiUserId(USER_ID)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('uses the login CSRF token for authenticated writes', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse({ csrfToken: 'csrf-from-login' }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))

    await login('operator', 'correct horse battery staple')
    await cancelTask('task-1')

    const loginHeaders = new Headers(vi.mocked(fetch).mock.calls[0][1]?.headers)
    const writeHeaders = new Headers(vi.mocked(fetch).mock.calls[1][1]?.headers)
    expect(loginHeaders.has('X-User-Id')).toBe(false)
    expect(writeHeaders.get('X-CSRF-Token')).toBe('csrf-from-login')
    expect(writeHeaders.get('X-User-Id')).toBe(USER_ID)
  })

  it('keeps an explicit administrator identity local to its own request', async () => {
    vi.mocked(fetch).mockImplementation(async (input) => {
      const url = String(input)
      return jsonResponse(url.includes('/admin/operations') ? {} : [])
    })

    await Promise.all([getOperations(ADMIN_ID), getTasks()])

    const calls = vi.mocked(fetch).mock.calls
    const adminCall = calls.find(([input]) => String(input).includes('/admin/operations'))
    const taskCall = calls.find(([input]) => String(input).endsWith('/tasks'))
    expect(new Headers(adminCall?.[1]?.headers).get('X-User-Id')).toBe(ADMIN_ID)
    expect(new Headers(taskCall?.[1]?.headers).get('X-User-Id')).toBe(USER_ID)
  })

  it('updates automatic prompt confirmation with the runtime config version', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({
      version: 4,
      config: { promptConfirmationRequired: false },
    }))

    await setPromptAutoConfirmation(ADMIN_ID, 3, true)

    const call = vi.mocked(fetch).mock.calls[0]
    expect(String(call[0])).toBe('/api/v1/admin/prompt-confirmation')
    expect(call[1]?.method).toBe('POST')
    expect(new Headers(call[1]?.headers).get('X-User-Id')).toBe(ADMIN_ID)
    expect(JSON.parse(String(call[1]?.body))).toEqual({ expectedVersion: 3, automatic: true })
  })

  it('sends prompt edits and assistant instructions with the current task version', async () => {
    const task = { id: 'task-1', stateVersion: 7 } as Task
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse(task))
      .mockResolvedValueOnce(jsonResponse({ task, advice: '建议增加正面特写' }))

    await saveTaskPrompts(task, '稳定提示词', '动态提示词')
    await runPromptAssistant(task, 'ADVISE', '增加正面特写', '稳定提示词', '动态提示词', 'STABLE')

    const saveBody = JSON.parse(String(vi.mocked(fetch).mock.calls[0][1]?.body))
    const assistantBody = JSON.parse(String(vi.mocked(fetch).mock.calls[1][1]?.body))
    expect(saveBody).toEqual({
      expectedStateVersion: 7,
      stablePrompt: '稳定提示词',
      dynamicPrompt: '动态提示词',
    })
    expect(assistantBody).toEqual({
      expectedStateVersion: 7,
      action: 'ADVISE',
      instruction: '增加正面特写',
      stablePrompt: '稳定提示词',
      dynamicPrompt: '动态提示词',
      targetVariant: 'STABLE',
    })
  })

  it('sends the ordinary user output-version choice when creating a task', async () => {
    const task = { id: 'task-1', variants: [{ kind: 'DYNAMIC' }] } as Task
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(task))

    await createTask(
      '动态广告',
      '突出开场动作',
      [{ id: 'upload-1' } as UploadResult],
      [],
      { analysisModel: 'gpt-5.6-sol', generationProvider: 'kling', variants: ['DYNAMIC'] },
    )

    const body = JSON.parse(String(vi.mocked(fetch).mock.calls[0][1]?.body))
    expect(body.variants).toEqual(['DYNAMIC'])
  })

  it('accepts quality-review risk as part of confirming the fixed A/B generation flow', async () => {
    const task = {
      id: 'task-1',
      stateVersion: 7,
      consistencyLevel: 'QUALITY_REVIEW',
    } as Task
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(task))

    await confirmTask(task)

    expect(JSON.parse(String(vi.mocked(fetch).mock.calls[0][1]?.body))).toEqual({
      expectedStateVersion: 7,
      acceptRisk: true,
    })
  })

  it('sends the selected output variants when confirming a task', async () => {
    const task = {
      id: 'task-1',
      stateVersion: 7,
      consistencyLevel: 'PASS',
    } as Task
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(task))

    await confirmTask(task, ['STABLE'])

    expect(JSON.parse(String(vi.mocked(fetch).mock.calls[0][1]?.body))).toEqual({
      expectedStateVersion: 7,
      acceptRisk: false,
      variants: ['STABLE'],
    })
  })

  it('sends idempotent per-variant generation feedback', async () => {
    const task = { id: 'task-1' } as Task
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(task))

    await setVariantFeedback('task-1', 'variant-a', 'LIKE')

    const call = vi.mocked(fetch).mock.calls[0]
    expect(String(call[0])).toBe('/api/v1/tasks/task-1/variants/variant-a/feedback')
    expect(call[1]?.method).toBe('PUT')
    expect(JSON.parse(String(call[1]?.body))).toEqual({ feedback: 'LIKE' })
  })

  it('exposes the next task cursor from the response header', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify([]), {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
        'X-Next-Cursor': 'next-page-token',
      },
    }))

    const page = await getTaskPage('current-page-token')

    expect(page).toEqual({ items: [], nextCursor: 'next-page-token' })
    expect(String(vi.mocked(fetch).mock.calls[0][0])).toBe(
      '/api/v1/tasks?cursor=current-page-token',
    )
  })

  it('uses administrator identity and idempotency for LibTV account switching', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse({ available: true, authenticated: false, accounts: [] }))
      .mockResolvedValueOnce(jsonResponse({ loginUrl: 'https://www.liblib.tv/zh' }))
      .mockResolvedValueOnce(jsonResponse({ ok: true, accountId: '202' }))

    await getLibTVAccountStatus(ADMIN_ID)
    await startLibTVLogin(ADMIN_ID)
    await switchLibTVAccount(ADMIN_ID, '202')

    const calls = vi.mocked(fetch).mock.calls
    expect(String(calls[0][0])).toBe('/api/v1/admin/libtv-account')
    expect(String(calls[1][0])).toBe('/api/v1/admin/libtv-login/start')
    expect(String(calls[2][0])).toBe('/api/v1/admin/libtv-account/use')
    for (const call of calls) {
      expect(new Headers(call[1]?.headers).get('X-User-Id')).toBe(ADMIN_ID)
    }
    expect(new Headers(calls[1][1]?.headers).has('Idempotency-Key')).toBe(false)
    expect(new Headers(calls[2][1]?.headers).get('Idempotency-Key')).toBeTruthy()
    expect(JSON.parse(String(calls[2][1]?.body))).toEqual({ account: '202' })
  })

  it('uses administrator identity for Kling login and logout', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse({ authenticated: true }))
      .mockResolvedValueOnce(jsonResponse({ authenticated: false }))

    await loginKling(ADMIN_ID)
    await logoutKling(ADMIN_ID)

    const calls = vi.mocked(fetch).mock.calls
    expect(String(calls[0][0])).toBe('/api/v1/admin/kling/login')
    expect(String(calls[1][0])).toBe('/api/v1/admin/kling/logout')
    for (const call of calls) {
      expect(call[1]?.method).toBe('POST')
      expect(new Headers(call[1]?.headers).get('X-User-Id')).toBe(ADMIN_ID)
    }
  })

  it('supports administrator account creation, password reset, and deactivation', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(jsonResponse({ id: 'user-1', username: 'designer-01' }, 201))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))

    await getAdminUsers(ADMIN_ID)
    await createAdminUser(ADMIN_ID, {
      username: 'designer-01',
      password: 'temporary-password',
    })
    await resetAdminUserPassword(ADMIN_ID, 'user-1', 'replacement-password')
    await deactivateAdminUser(ADMIN_ID, 'user-1')

    const calls = vi.mocked(fetch).mock.calls
    expect(String(calls[0][0])).toBe('/api/v1/admin/users')
    expect(String(calls[1][0])).toBe('/api/v1/admin/users')
    expect(calls[1][1]?.method).toBe('POST')
    expect(JSON.parse(String(calls[1][1]?.body))).toEqual({
      username: 'designer-01',
      password: 'temporary-password',
    })
    expect(String(calls[2][0])).toBe('/api/v1/admin/users/user-1/reset-password')
    expect(calls[2][1]?.method).toBe('POST')
    expect(JSON.parse(String(calls[2][1]?.body))).toEqual({
      password: 'replacement-password',
    })
    expect(String(calls[3][0])).toBe('/api/v1/admin/users/user-1')
    expect(calls[3][1]?.method).toBe('DELETE')
  })
})
