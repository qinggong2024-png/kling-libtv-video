import { getCurrentUser, getSystemStatus } from '../../api'
import { createUuid } from '../../uuid'

export type DirectorCommandAction = 'analyze' | 'select_direction' | 'authorize' | 'generate' | 'review' | 'select'

export interface DirectorCandidate {
  candidate_id: string
  package_id: string
  authorization_id: string
  shot_id: string
  batch_id: string
  item_id: string
  output_id: string
  synthetic: boolean
  qualified: boolean
  revision_index: number
  sha256: string
  object_key: string
  media_evidence: string
}

export interface DirectorLatestReview {
  candidate_id: string
  reviewer_id: string
  decision: 'QUALIFIED' | 'REJECTED'
  qualification_scope: 'OFFLINE_SYNTHETIC_ONLY'
  reason: string | null
}

export interface DirectorTaskSnapshot {
  asset: { sha256: string; width: number; height: number; object_key: string }
  trace: string[]
  candidates: DirectorCandidate[]
  calls: number
  cost_micros: number
  total_calls: number
  total_cost_micros: number
  plan?: {
    directions: Array<{ id: 'A' | 'B' | 'C'; scene: string; behavior: string }>
    selected_direction?: 'A' | 'B' | 'C' | null
  }
  package?: {
    package_id: string
    revision: number
    parent_package_id: string | null
    locks_hash: string
    facts_revision: number
    preservation_hash: string
    ruleset: string
    shot_id: 'FIRST_FRAME'
    prompt: string
    reality: Array<{ dimension: string; decision: string; evidence: string }>
  }
  authorization?: {
    authorization_id: string
    package_id: string
    locks_hash: string
    expires_at: string
  }
  execution_state?: string
  stop_reason?: string
  stopped?: boolean
  latest_review?: DirectorLatestReview
  selection?: {
    candidate_id: string
    package_id: string
    shot_id: 'FIRST_FRAME'
    synthetic: true
  }
}

export interface DirectorTaskResponse {
  id: string
  status: string
  state_version: number
  snapshot: DirectorTaskSnapshot
  mode: 'OFFLINE_FAKE_ONLY' | string
}

export interface DirectorCommandInput {
  command_key?: string
  expected_version: number
  action: DirectorCommandAction
  direction_id?: 'A' | 'B' | 'C'
  package_id?: string
  candidate_id?: string
  decision?: 'QUALIFIED' | 'REJECTED'
  reason?: string
  authorization?: {
    authorization_id: string
    package_id: string
    locks_hash: string
    scope: 'FIRST_FRAME'
    shot_ids: ['FIRST_FRAME']
    expires_at: string
    loop_enabled: false
    max_revisions: 0
    max_calls: 6
    max_cost_micros: 6
    currency: 'FAKE'
    allowed_modules: ['Reality']
  }
}

export class DirectorApiError extends Error {
  readonly status: number
  readonly code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.name = 'DirectorApiError'
    this.status = status
    this.code = code
  }
}

function readCookie(name: string): string {
  if (typeof document === 'undefined') return ''
  const prefix = `${encodeURIComponent(name)}=`
  const match = document.cookie.split('; ').find((item) => item.startsWith(prefix))
  return match ? decodeURIComponent(match.slice(prefix.length)) : ''
}

async function authHeaders(): Promise<Headers> {
  const system = await getSystemStatus()
  const headers = new Headers()
  if (!system.sharedAuthentication) {
    const user = await getCurrentUser()
    headers.set('X-User-Id', user.userId)
  }
  const csrfToken = readCookie(system.csrfCookieName)
  if (csrfToken) headers.set('X-CSRF-Token', csrfToken)
  return headers
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = await authHeaders()
  new Headers(init.headers).forEach((value, key) => headers.set(key, value))
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    headers,
    credentials: 'include',
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: unknown } | null
    const detail = body?.detail
    const payload = detail && typeof detail === 'object' ? detail as { code?: unknown; message?: unknown } : null
    const code = typeof payload?.code === 'string' ? payload.code : 'DIRECTOR_REQUEST_FAILED'
    const message = typeof payload?.message === 'string'
      ? payload.message
      : typeof detail === 'string' ? detail : `导演接口请求失败（${response.status}）`
    throw new DirectorApiError(response.status, code, message)
  }
  return response.json() as Promise<T>
}

export function createDirectorProduct(internalSkuId: string): Promise<{ id: string }> {
  return request<{ id: string }>('/products', {
    method: 'POST',
    body: JSON.stringify({ internalSkuId }),
  })
}

export function createDirectorTask(input: {
  productId: string
  front: File
  clientKey: string
}): Promise<DirectorTaskResponse> {
  const body = new FormData()
  body.append('product_id', input.productId)
  body.append('client_key', input.clientKey)
  body.append('front', input.front, input.front.name)
  return request<DirectorTaskResponse>('/creative-workflow/tasks', { method: 'POST', body })
}

export function getDirectorTask(taskId: string): Promise<DirectorTaskResponse> {
  return request<DirectorTaskResponse>(`/creative-workflow/tasks/${encodeURIComponent(taskId)}`)
}

export function sendDirectorCommand(
  taskId: string,
  input: DirectorCommandInput,
): Promise<DirectorTaskResponse> {
  return request<DirectorTaskResponse>(
    `/creative-workflow/tasks/${encodeURIComponent(taskId)}/commands`,
    {
      method: 'POST',
      body: JSON.stringify({
        command_key: input.command_key ?? createUuid(),
        expected_version: input.expected_version,
        action: input.action,
        ...(input.direction_id ? { direction_id: input.direction_id } : {}),
        ...(input.package_id ? { package_id: input.package_id } : {}),
        ...(input.candidate_id ? { candidate_id: input.candidate_id } : {}),
        ...(input.decision ? { decision: input.decision } : {}),
        ...(input.reason ? { reason: input.reason } : {}),
        ...(input.authorization ? { authorization: input.authorization } : {}),
      }),
    },
  )
}
