import { ApiError } from './api'

export async function settleSessionRefresh<Page, Actor>(page: Promise<Page>, actor: Promise<Actor>) {
  const results = await Promise.allSettled([page, actor] as const)
  // Authentication failure takes precedence over partial data and server errors.
  for (const result of results) {
    if (result.status === 'rejected' && result.reason instanceof ApiError && result.reason.status === 401) {
      throw result.reason
    }
  }
  return results
}
