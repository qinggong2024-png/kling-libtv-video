import type { AdminCredentialsStatus, AdminUser, AuthUser, BatchConfirmationResponse, FeedbackReason, FeedbackValue, FixedVideoTaskOptions, KlingConfig, KlingConfigPatch, KlingElement, KlingElementCreate, KlingElementList, KlingStatus, LibTVAccountStatus, LibTVAccountSwitch, LibTVLoginStart, MotionActionSummary, OperationsSnapshot, PromptAssistantResponse, Reconciliation, RuntimeConfigSnapshot, SiteStyleProfileSummary, SystemStatus, Task, UploadResult, VariantKind, VideoTemplateSummary } from './types'
import { createUuid } from './uuid'

const DEFAULT_USER_ID = '00000000-0000-0000-0000-000000000001'
const DEFAULT_TIMEOUT_MS = 30_000
const UPLOAD_TIMEOUT_MS = 60_000
const LONG_RUNNING_TIMEOUT_MS = 120_000
const DOWNLOAD_TIMEOUT_MS = 300_000
let developmentUserId: string | null = DEFAULT_USER_ID
let csrfCookieName = 'libtv_csrf'
let csrfToken = ''

type RequestPolicy = {
  authenticate?: boolean
  actorId?: string | null
  timeoutMs?: number
  onResponse?: (response: Response) => void
}

export class ApiError extends Error {
  code: string
  status: number
  details: unknown
  retryable: boolean | null

  constructor(
    status: number,
    code: string,
    message: string,
    details: unknown = null,
    retryable: boolean | null = null,
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
    this.retryable = retryable
  }
}

export function setApiUserId(value: string | null) {
  developmentUserId = value
}

export function setCsrfCookieName(value: string | null) {
  if (value) csrfCookieName = value
}

function readCookie(name: string): string {
  if (typeof document === 'undefined') return ''
  const prefix = `${encodeURIComponent(name)}=`
  const match = document.cookie.split('; ').find((item) => item.startsWith(prefix))
  return match ? decodeURIComponent(match.slice(prefix.length)) : ''
}

type ErrorPayload = {
  code?: unknown
  message?: unknown
  details?: unknown
  retryable?: unknown
}

function validationDetailMessage(detail: unknown[]): string {
  const messages = detail.flatMap((item) => {
    if (typeof item === 'string') return [item]
    if (!item || typeof item !== 'object') return []
    const entry = item as { loc?: unknown; msg?: unknown }
    if (typeof entry.msg !== 'string') return []
    const location = Array.isArray(entry.loc)
      ? entry.loc.filter((part) => part !== 'body').join('.')
      : ''
    return [location ? `${location}: ${entry.msg}` : entry.msg]
  })
  return messages.join('；')
}

function apiErrorFromBody(status: number, statusText: string, body: unknown): ApiError {
  const envelope = body && typeof body === 'object' && !Array.isArray(body)
    ? body as Record<string, unknown>
    : {}
  const rawDetail = envelope.detail ?? envelope.error ?? body
  if (typeof rawDetail === 'string') {
    return new ApiError(status, 'REQUEST_FAILED', rawDetail)
  }
  if (Array.isArray(rawDetail)) {
    return new ApiError(
      status,
      'VALIDATION_FAILED',
      validationDetailMessage(rawDetail) || `${status} ${statusText}`,
      rawDetail,
      false,
    )
  }
  const detail = rawDetail && typeof rawDetail === 'object'
    ? rawDetail as ErrorPayload
    : {}
  return new ApiError(
    status,
    typeof detail.code === 'string' ? detail.code : 'REQUEST_FAILED',
    typeof detail.message === 'string' ? detail.message : `${status} ${statusText}`,
    detail.details ?? null,
    typeof detail.retryable === 'boolean' ? detail.retryable : null,
  )
}

async function fetchResponse(path: string, init: RequestInit = {}, policy: RequestPolicy = {}): Promise<Response> {
  const { authenticate = true, actorId = developmentUserId, timeoutMs = DEFAULT_TIMEOUT_MS } = policy
  const headers = new Headers(init.headers)
  if (authenticate && actorId) headers.set('X-User-Id', actorId)
  if (['POST', 'PUT', 'PATCH', 'DELETE'].includes((init.method ?? 'GET').toUpperCase())) {
    const token = csrfToken || readCookie(csrfCookieName)
    if (token) headers.set('X-CSRF-Token', token)
  }
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const controller = new AbortController()
  let timedOut = false
  const abortFromCaller = () => controller.abort(init.signal?.reason)
  if (init.signal?.aborted) abortFromCaller()
  else init.signal?.addEventListener('abort', abortFromCaller, { once: true })
  const timeout = window.setTimeout(() => {
    timedOut = true
    controller.abort()
  }, timeoutMs)
  let response: Response
  try {
    response = await fetch(path, { ...init, headers, credentials: 'include', signal: controller.signal })
  } catch (cause) {
    if (timedOut && cause instanceof DOMException && cause.name === 'AbortError') {
      throw new ApiError(408, 'REQUEST_TIMEOUT', `生产服务在 ${Math.round(timeoutMs / 1000)} 秒内未响应`)
    }
    throw cause
  } finally {
    window.clearTimeout(timeout)
    init.signal?.removeEventListener('abort', abortFromCaller)
  }
  policy.onResponse?.(response)
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw apiErrorFromBody(response.status, response.statusText, body)
  }
  return response
}

async function request<T>(path: string, init: RequestInit = {}, policy: RequestPolicy = {}): Promise<T> {
  const response = await fetchResponse(path, init, policy)
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

async function requestBlob(path: string, policy: RequestPolicy = {}): Promise<Blob> {
  const response = await fetchResponse(path, {}, policy)
  return response.blob()
}

const key = () => createUuid()

export const getSystemStatus = () => request<SystemStatus>('/api/v1/system/status', {}, { authenticate: false })
export const getCurrentUser = () => request<AuthUser>('/api/v1/auth/me')
export const getPersonalPromptAutoConfirmation = () => request<{ automatic: boolean }>('/api/v1/auth/preferences/prompt-confirmation')
export const setPersonalPromptAutoConfirmation = (automatic: boolean) => request<{ automatic: boolean }>('/api/v1/auth/preferences/prompt-confirmation', {
  method: 'PATCH',
  body: JSON.stringify({ automatic }),
})
export type TaskPage = { items: Task[]; nextCursor: string | null }

export async function getTaskPage(cursor?: string): Promise<TaskPage> {
  let nextCursor: string | null = null
  const query = cursor ? `?cursor=${encodeURIComponent(cursor)}` : ''
  const items = await request<Task[]>(`/api/v1/tasks${query}`, {}, {
    onResponse: (response) => {
      nextCursor = response.headers.get('X-Next-Cursor')
    },
  })
  return { items, nextCursor }
}

export const getTasks = async () => (await getTaskPage()).items
export const getTask = (taskId: string) => request<Task>(`/api/v1/tasks/${taskId}`)

export const setVariantFeedback = (
  taskId: string,
  variantId: string,
  feedback: FeedbackValue | null,
  details?: { reasons: FeedbackReason[]; comment: string | null },
) => request<Task>(`/api/v1/tasks/${taskId}/variants/${variantId}/feedback`, {
  method: 'PUT',
  body: JSON.stringify({ feedback, ...details }),
})

export async function login(username: string, password: string): Promise<void> {
  const result = await request<{ csrfToken: string }>('/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  }, { authenticate: false })
  csrfToken = result.csrfToken
}

export async function logout(): Promise<void> {
  await request<void>('/api/v1/auth/logout', { method: 'POST' })
  csrfToken = ''
}

export function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  return request<void>('/api/v1/auth/password', {
    method: 'POST',
    body: JSON.stringify({ currentPassword, newPassword }),
  })
}

export async function uploadStoryboard(file: File, signal?: AbortSignal): Promise<UploadResult> {
  const body = new FormData()
  body.append('file', file)
  return request('/api/v1/uploads', { method: 'POST', body, headers: { 'Idempotency-Key': key() }, signal }, { timeoutMs: UPLOAD_TIMEOUT_MS })
}

export function getVideoTemplates(): Promise<VideoTemplateSummary[]> {
  return request('/api/v1/video-templates')
}

export function getSiteStyleProfiles(): Promise<SiteStyleProfileSummary[]> {
  return request('/api/v1/site-style-profiles')
}

export function getMotionActions(): Promise<MotionActionSummary[]> {
  return request('/api/v1/motion-actions')
}

export function createTask(
  title: string,
  requirement: string,
  uploads: UploadResult[],
  productUploads: UploadResult[],
  preferences: { analysisModel: string; generationProvider: 'libtv' | 'kling'; variants: VariantKind[] },
  sourceUploadDurationSeconds = 0,
) {
  return request<Task>('/api/v1/tasks', {
    method: 'POST',
    headers: { 'Idempotency-Key': key() },
    body: JSON.stringify({
      clientTaskId: createUuid(),
      title,
      userRequirement: requirement,
      analysisModel: preferences.analysisModel,
      generationProvider: preferences.generationProvider,
      sourceUploadDurationSeconds,
      generationPreset: 'DEFAULT_10S_9X16',
      variants: preferences.variants,
      storyboards: uploads.map((upload, index) => ({ uploadId: upload.id, order: index + 1, required: true })),
      productImages: productUploads.map((upload, index) => ({ uploadId: upload.id, order: index + 1 })),
    }),
  })
}

export function createVideoTask(
  title: string,
  uploads: UploadResult[],
  options: FixedVideoTaskOptions,
  sourceUploadDurationSeconds = 0,
) {
  return request<Task>('/api/v1/video-tasks', {
    method: 'POST',
    headers: { 'Idempotency-Key': key() },
    body: JSON.stringify({
      clientTaskId: createUuid(),
      title,
      storyboards: uploads.map((upload, index) => ({ uploadId: upload.id, order: index + 1, required: true })),
      templateId: options.templateId,
      siteProfileId: options.siteProfileId,
      elementIds: options.elementIds,
      resultCount: options.resultCount,
      actionIntensity: options.actionIntensity,
      cameraTempo: options.cameraTempo,
      cutMode: options.cutMode,
      paidSubmissionConsent: true,
      sourceUploadDurationSeconds,
    }),
  })
}

export function reuseTask(task: Task, variants: VariantKind[]) {
  return request<Task>(`/api/v1/tasks/${task.id}/reuse`, {
    method: 'POST',
    headers: { 'Idempotency-Key': key() },
    body: JSON.stringify({
      clientTaskId: createUuid(),
      title: `${task.title} · 复用`,
      expectedSourceStateVersion: task.stateVersion,
      variants,
    }),
  })
}

export const analyzeTask = (task: Task) => request<Task>(`/api/v1/tasks/${task.id}/analyze`, {
  method: 'POST',
  headers: { 'Idempotency-Key': key() },
  body: JSON.stringify({ expectedStateVersion: task.stateVersion }),
})

export const confirmTask = (task: Task, variants?: VariantKind[]) => request<Task>(`/api/v1/tasks/${task.id}/confirm`, {
  method: 'POST',
  headers: { 'Idempotency-Key': key() },
  body: JSON.stringify({
    expectedStateVersion: task.stateVersion,
    acceptRisk: task.consistencyLevel === 'QUALITY_REVIEW',
    ...(variants ? { variants } : {}),
  }),
}, { timeoutMs: LONG_RUNNING_TIMEOUT_MS })

export const saveTaskPrompts = (task: Task, stablePrompt: string, dynamicPrompt: string) => request<Task>(`/api/v1/tasks/${task.id}/prompts`, {
  method: 'PATCH',
  body: JSON.stringify({
    expectedStateVersion: task.stateVersion,
    stablePrompt,
    dynamicPrompt,
  }),
})

export const runPromptAssistant = (
  task: Task,
  action: 'REGENERATE' | 'ADVISE',
  instruction: string,
  stablePrompt: string,
  dynamicPrompt: string,
  targetVariant?: VariantKind,
) => request<PromptAssistantResponse>(`/api/v1/tasks/${task.id}/prompt-assistant`, {
  method: 'POST',
  body: JSON.stringify({
    expectedStateVersion: task.stateVersion,
    action,
    instruction,
    stablePrompt,
    dynamicPrompt,
    targetVariant,
  }),
}, { timeoutMs: LONG_RUNNING_TIMEOUT_MS })

export const cancelTask = (taskId: string) => request<void>(`/api/v1/tasks/${taskId}/cancel`, {
  method: 'POST',
  headers: { 'Idempotency-Key': key() },
})

export const confirmTasks = (tasks: Task[]) => request<BatchConfirmationResponse>('/api/v1/confirmations/execute', {
  method: 'POST',
  headers: { 'Idempotency-Key': key() },
  body: JSON.stringify({ tasks: tasks.map((task) => ({ taskId: task.id, expectedStateVersion: task.stateVersion, acceptRisk: task.consistencyLevel === 'QUALITY_REVIEW' })) }),
}, { timeoutMs: LONG_RUNNING_TIMEOUT_MS })

export const restoreOutput = (taskId: string, variant: VariantKind) => request<{ artifactId: string; downloadUrl: string }>(`/api/v1/tasks/${taskId}/restore-remote-output`, {
  method: 'POST',
  headers: { 'Idempotency-Key': key() },
  body: JSON.stringify({ variant }),
}, { timeoutMs: LONG_RUNNING_TIMEOUT_MS })

export const downloadUrl = (artifactId: string) => `/api/v1/downloads/${artifactId}`

export async function saveArtifact(artifactId: string, filename: string): Promise<void> {
  const url = URL.createObjectURL(await requestBlob(downloadUrl(artifactId), { timeoutMs: DOWNLOAD_TIMEOUT_MS }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

export async function fetchAssetObjectUrl(path: string): Promise<string> {
  return URL.createObjectURL(await requestBlob(path, { timeoutMs: UPLOAD_TIMEOUT_MS }))
}

export async function fetchAssetFile(path: string, filename: string): Promise<File> {
  const blob = await requestBlob(path, { timeoutMs: UPLOAD_TIMEOUT_MS })
  return new File([blob], filename, { type: blob.type || 'image/jpeg' })
}

export async function fetchArtifactObjectUrl(artifactId: string): Promise<string> {
  return URL.createObjectURL(await requestBlob(downloadUrl(artifactId), { timeoutMs: DOWNLOAD_TIMEOUT_MS }))
}

export async function getReconciliations(adminId: string | null): Promise<Reconciliation[]> {
  if (!adminId) return []
  return request('/api/v1/admin/reconciliations', {}, { actorId: adminId })
}

export async function reconcileAttempt(adminId: string, attemptId: string): Promise<void> {
  await request(`/api/v1/admin/reconciliations/${attemptId}/classify`, { method: 'POST', headers: { 'Idempotency-Key': key() }, body: JSON.stringify({ action: 'RECONCILE' }) }, { actorId: adminId })
}

export function getOperations(adminId: string): Promise<OperationsSnapshot> {
  return request('/api/v1/admin/operations', {}, { actorId: adminId })
}

export function getAdminUsers(adminId: string): Promise<AdminUser[]> {
  return request('/api/v1/admin/users', {}, { actorId: adminId })
}

export function createAdminUser(
  adminId: string,
  values: { username: string; password: string },
): Promise<AdminUser> {
  return request('/api/v1/admin/users', {
    method: 'POST',
    body: JSON.stringify(values),
  }, { actorId: adminId })
}

export function resetAdminUserPassword(
  adminId: string,
  userId: string,
  password: string,
): Promise<void> {
  return request(`/api/v1/admin/users/${userId}/reset-password`, {
    method: 'POST',
    body: JSON.stringify({ password }),
  }, { actorId: adminId })
}

export function deactivateAdminUser(adminId: string, userId: string): Promise<void> {
  return request(`/api/v1/admin/users/${userId}`, {
    method: 'DELETE',
  }, { actorId: adminId })
}

export function getAdminCredentials(adminId: string | null): Promise<AdminCredentialsStatus> {
  return adminId
    ? request('/api/v1/admin/credentials', {}, { actorId: adminId })
    : request('/api/v1/admin/credentials')
}

export function getLibTVAccountStatus(adminId: string): Promise<LibTVAccountStatus> {
  return request('/api/v1/admin/libtv-account', {}, { actorId: adminId })
}

export function getKlingStatus(adminId: string): Promise<KlingStatus> {
  return request('/api/v1/admin/kling/status', {}, { actorId: adminId })
}

export function getKlingConfig(adminId: string): Promise<KlingConfig> {
  return request('/api/v1/admin/kling/config', {}, { actorId: adminId })
}

export function updateKlingConfig(adminId: string, values: KlingConfigPatch): Promise<KlingConfig> {
  return request('/api/v1/admin/kling/config', {
    method: 'PATCH',
    body: JSON.stringify(values),
  }, { actorId: adminId })
}

export function refreshKlingCapabilities(adminId: string): Promise<KlingStatus> {
  return request('/api/v1/admin/kling/capabilities/refresh', {
    method: 'POST',
  }, { actorId: adminId })
}

export function loginKling(adminId: string): Promise<KlingStatus> {
  return request('/api/v1/admin/kling/login', {
    method: 'POST',
  }, { actorId: adminId })
}

export function logoutKling(adminId: string): Promise<KlingStatus> {
  return request('/api/v1/admin/kling/logout', {
    method: 'POST',
  }, { actorId: adminId })
}

export function getKlingElements(
  adminId: string | null,
  pageNum = 1,
  pageSize = 50,
  official = false,
  signal?: AbortSignal,
): Promise<KlingElementList> {
  const query = new URLSearchParams({
    pageNum: String(pageNum),
    pageSize: String(pageSize),
    official: String(official),
  })
  return request(`/api/v1/admin/kling/elements?${query.toString()}`, { signal }, { actorId: adminId })
}

export function createKlingElement(adminId: string, values: KlingElementCreate): Promise<KlingElement> {
  return request('/api/v1/admin/kling/elements', {
    method: 'POST',
    body: JSON.stringify(values),
  }, { actorId: adminId, timeoutMs: LONG_RUNNING_TIMEOUT_MS })
}

export function deleteKlingElement(adminId: string, elementId: string): Promise<void> {
  return request(`/api/v1/admin/kling/elements/${encodeURIComponent(elementId)}`, {
    method: 'DELETE',
  }, { actorId: adminId, timeoutMs: LONG_RUNNING_TIMEOUT_MS })
}

export function startLibTVLogin(adminId: string): Promise<LibTVLoginStart> {
  return request('/api/v1/admin/libtv-login/start', {
    method: 'POST',
  }, { actorId: adminId })
}

export function switchLibTVAccount(adminId: string, account: string): Promise<LibTVAccountSwitch> {
  return request('/api/v1/admin/libtv-account/use', {
    method: 'POST',
    headers: { 'Idempotency-Key': key() },
    body: JSON.stringify({ account }),
  }, { actorId: adminId })
}

export function updateAdminCredentials(
  adminId: string | null,
  values: { libtvAccessKey?: string; modelApiKey?: string; modelBaseUrl?: string; clearModelBaseUrl?: boolean },
): Promise<AdminCredentialsStatus> {
  return request<AdminCredentialsStatus>('/api/v1/admin/credentials', {
    method: 'PATCH',
    body: JSON.stringify(values),
  }, { actorId: adminId })
}

export function setOperationalPause(
  adminId: string,
  expectedVersion: number,
  scope: 'GLOBAL' | 'PAID_SUBMISSIONS',
  paused: boolean,
  reason: string,
): Promise<{ version: number }> {
  return request('/api/v1/admin/pause', {
    method: 'POST',
    headers: { 'Idempotency-Key': key() },
    body: JSON.stringify({ expectedVersion, scope, paused, reason }),
  }, { actorId: adminId })
}

export function setPromptAutoConfirmation(
  adminId: string,
  expectedVersion: number,
  automatic: boolean,
): Promise<RuntimeConfigSnapshot> {
  return request('/api/v1/admin/prompt-confirmation', {
    method: 'POST',
    body: JSON.stringify({ expectedVersion, automatic }),
  }, { actorId: adminId })
}
