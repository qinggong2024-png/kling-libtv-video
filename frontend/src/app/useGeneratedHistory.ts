import { useCallback, useEffect, useState } from 'react'
import { getAllDirectorTaskHistory, getAllImageGenerationBatchHistory, getAllTaskHistory } from '../api'

export function startHistoryPolling<T>(
  read: (signal: AbortSignal) => Promise<T[]>,
  publish: (update: { loading: boolean; items?: T[]; error: string | null; syncedAt?: number }) => void,
) {
  const controller = new AbortController()
  let timer: ReturnType<typeof setTimeout> | undefined
  const load = async () => {
    if (controller.signal.aborted) return
    publish({ loading: true, error: null })
    try {
      const items = await read(controller.signal)
      if (!controller.signal.aborted) publish({ items, loading: false, error: null, syncedAt: Date.now() })
    } catch (cause) {
      if (!controller.signal.aborted) publish({ loading: false, error: cause instanceof Error ? cause.message : '历史读取失败' })
    } finally {
      if (!controller.signal.aborted) timer = setTimeout(() => void load(), 30_000)
    }
  }
  void Promise.resolve().then(load)
  return () => {
    controller.abort()
    clearTimeout(timer)
  }
}

function useHistorySource<T>(owner: string | null, enabled: boolean, revision: number, read: (signal?: AbortSignal) => Promise<T[]>) {
  const [state, setState] = useState<{ owner: string | null; items: T[]; loading: boolean; error: string | null; syncedAt: number | null }>({
    owner: null, items: [], loading: false, error: null, syncedAt: null,
  })
  useEffect(() => {
    if (!owner || !enabled) return
    return startHistoryPolling(read, (update) => setState((previous) => ({
      ...(previous.owner === owner ? previous : { owner, items: [], syncedAt: null }),
      ...update,
    })))
  }, [owner, enabled, revision, read])
  // Filter synchronously: an account change must never expose the previous owner.
  return owner && state.owner === owner ? state : { items: [] as T[], loading: Boolean(owner && enabled), error: null, syncedAt: null }
}

export function useGeneratedHistory(owner: string | null, enabled: boolean) {
  const [revision, setRevision] = useState(0)
  const refreshHistory = useCallback(() => setRevision((value) => value + 1), [])
  return {
    images: useHistorySource(owner, enabled, revision, getAllImageGenerationBatchHistory),
    videos: useHistorySource(owner, enabled, revision, getAllTaskHistory),
    directors: useHistorySource(owner, enabled, revision, getAllDirectorTaskHistory),
    refreshHistory,
  }
}
