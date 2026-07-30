import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, cancelTask, changePassword, confirmTask, createAdminUser, createKlingElement, createTask, createVideoTask, deactivateAdminUser, deleteKlingElement, getAdminUsers, getKlingConfig, getKlingElements, getLibTVAccountStatus, getOperations, getPersonalPromptAutoConfirmation, getTaskPage, getTasks, login, loginKling, logoutKling, resetAdminUserPassword, runPromptAssistant, saveArtifact, saveTaskPrompts, setApiUserId, setPersonalPromptAutoConfirmation, setPromptAutoConfirmation, setVariantFeedback, startLibTVLogin, switchLibTVAccount, updateKlingConfig } from './api'
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

  it('changes the current account password without an administrator target id', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse({ csrfToken: 'csrf-from-login' }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))

    await login('operator', 'current-password-1234')
    await changePassword('current-password-1234', 'replacement-password-1234')

    const call = vi.mocked(fetch).mock.calls[1]
    expect(String(call[0])).toBe('/api/v1/auth/password')
    expect(call[1]?.method).toBe('POST')
    expect(new Headers(call[1]?.headers).get('X-CSRF-Token')).toBe('csrf-from-login')
    expect(JSON.parse(String(call[1]?.body))).toEqual({
      currentPassword: 'current-password-1234',
      newPassword: 'replacement-password-1234',
    })
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

  it('reads and updates the current user prompt confirmation preference', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse({ automatic: false }))
      .mockResolvedValueOnce(jsonResponse({ automatic: true }))

    await getPersonalPromptAutoConfirmation()
    await setPersonalPromptAutoConfirmation(true)

    const calls = vi.mocked(fetch).mock.calls
    expect(String(calls[0][0])).toBe('/api/v1/auth/preferences/prompt-confirmation')
    expect(calls[0][1]?.method).toBeUndefined()
    expect(String(calls[1][0])).toBe('/api/v1/auth/preferences/prompt-confirmation')
    expect(calls[1][1]?.method).toBe('PATCH')
    expect(new Headers(calls[1][1]?.headers).get('X-User-Id')).toBe(USER_ID)
    expect(JSON.parse(String(calls[1][1]?.body))).toEqual({ automatic: true })
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

  it('maps historical elements and newly uploaded subject images for a fixed video task', async () => {
    const task = { id: 'task-fixed' } as Task
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(task, 201))

    await createVideoTask(
      '固定模板视频',
      [{ id: 'upload-1' } as UploadResult],
      {
        templateId: 'template-1',
        siteProfileId: 'site-1',
        elementIds: [],
        subjectUploads: [
          { id: 'subject-front' } as UploadResult,
          { id: 'subject-back' } as UploadResult,
        ],
        resultCount: 1,
        actionIntensity: 'standard',
        cameraTempo: 'standard',
        cutMode: 'explicit_cuts',
      },
    )

    expect(JSON.parse(String(vi.mocked(fetch).mock.calls[0][1]?.body))).toMatchObject({
      elementIds: [],
      subjectImages: [
        { uploadId: 'subject-front', order: 1 },
        { uploadId: 'subject-back', order: 2 },
      ],
    })
  })

  it('accepts quality-review risk as part of confirming the fixed dual-result generation flow', async () => {
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

  it('sends optional detailed generation feedback', async () => {
    const task = { id: 'task-1' } as Task
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(task))

    await setVariantFeedback('task-1', 'variant-a', 'DISLIKE', {
      reasons: ['CAMERA_TOO_FAST', 'PRODUCT_UNCLEAR'],
      comment: '最后一个镜头商品不够清楚',
    })

    const call = vi.mocked(fetch).mock.calls[0]
    expect(JSON.parse(String(call[1]?.body))).toEqual({
      feedback: 'DISLIKE',
      reasons: ['CAMERA_TOO_FAST', 'PRODUCT_UNCLEAR'],
      comment: '最后一个镜头商品不够清楚',
    })
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

  it('reads and updates the administrator Kling provider configuration', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse({ backend: 'api', apiKeyConfigured: false }))
      .mockResolvedValueOnce(jsonResponse({ backend: 'api', apiKeyConfigured: true }))

    await getKlingConfig(ADMIN_ID)
    await updateKlingConfig(ADMIN_ID, {
      backend: 'api',
      apiKey: 'secret-kling-key',
      model: 'kling-3.0-omni',
      duration: 10,
      aspectRatio: '9:16',
      resolution: '1080p',
      audio: 'off',
      multiShot: true,
      maxSubmitConcurrency: 2,
      maxPollConcurrency: 6,
      enabled: true,
    })

    const calls = vi.mocked(fetch).mock.calls
    expect(String(calls[0][0])).toBe('/api/v1/admin/kling/config')
    expect(calls[0][1]?.method).toBeUndefined()
    expect(String(calls[1][0])).toBe('/api/v1/admin/kling/config')
    expect(calls[1][1]?.method).toBe('PATCH')
    expect(new Headers(calls[1][1]?.headers).get('X-User-Id')).toBe(ADMIN_ID)
    expect(JSON.parse(String(calls[1][1]?.body))).toEqual({
      backend: 'api',
      apiKey: 'secret-kling-key',
      model: 'kling-3.0-omni',
      duration: 10,
      aspectRatio: '9:16',
      resolution: '1080p',
      audio: 'off',
      multiShot: true,
      maxSubmitConcurrency: 2,
      maxPollConcurrency: 6,
      enabled: true,
    })
  })

  it('creates, lists, and deletes Kling elements without logging reference payloads', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse({ id: 'element-1', status: 'submitted' }, 201))
      .mockResolvedValueOnce(jsonResponse({
        items: [{ id: 'element-1', status: 'active' }],
        pageNum: 2,
        pageSize: 25,
        total: 1,
        official: false,
      }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))

    await createKlingElement(ADMIN_ID, {
      name: '春季女装模特',
      description: '正面与侧面参考',
      imageReferences: ['base64-front', 'base64-side'],
      voiceId: 'voice-1',
    })
    const page = await getKlingElements(ADMIN_ID, 2, 25, false)
    await deleteKlingElement(ADMIN_ID, 'element-1')

    const calls = vi.mocked(fetch).mock.calls
    expect(String(calls[0][0])).toBe('/api/v1/admin/kling/elements')
    expect(calls[0][1]?.method).toBe('POST')
    expect(JSON.parse(String(calls[0][1]?.body))).toEqual({
      name: '春季女装模特',
      description: '正面与侧面参考',
      imageReferences: ['base64-front', 'base64-side'],
      voiceId: 'voice-1',
    })
    expect(String(calls[1][0])).toBe('/api/v1/admin/kling/elements?pageNum=2&pageSize=25&official=false')
    expect(page.total).toBe(1)
    expect(String(calls[2][0])).toBe('/api/v1/admin/kling/elements/element-1')
    expect(calls[2][1]?.method).toBe('DELETE')
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

  it('preserves a FastAPI string detail message', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ detail: 'administrator role is required' }, 403))

    await expect(getOperations(ADMIN_ID)).rejects.toMatchObject({
      status: 403,
      code: 'REQUEST_FAILED',
      message: 'administrator role is required',
    })
  })

  it('formats FastAPI validation detail arrays', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({
      detail: [{ loc: ['body', 'duration'], msg: 'Input should be less than or equal to 15' }],
    }, 422))

    await expect(updateKlingConfig(ADMIN_ID, { duration: 16 })).rejects.toMatchObject({
      status: 422,
      code: 'VALIDATION_FAILED',
      message: 'duration: Input should be less than or equal to 15',
    })
  })

  it('preserves structured error details and retryability', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({
      detail: {
        code: 'KLING_API_RATE_LIMITED',
        message: 'Too many requests',
        details: { retryAfterSeconds: 30 },
        retryable: true,
      },
    }, 429))

    const error = await getTasks().catch((cause: unknown) => cause)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({
      status: 429,
      code: 'KLING_API_RATE_LIMITED',
      message: 'Too many requests',
      details: { retryAfterSeconds: 30 },
      retryable: true,
    })
  })

  it('uses the shared error parser for artifact downloads', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({
      detail: 'server copy has expired; use remote restore',
    }, 410))

    await expect(saveArtifact('artifact-1', 'video.mp4')).rejects.toMatchObject({
      status: 410,
      message: 'server copy has expired; use remote restore',
    })
  })
})
