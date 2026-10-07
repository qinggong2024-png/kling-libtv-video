// 本文件由 App.tsx 拆分生成（2026-09-21 前端架构拆分 v1）。
// 逐字搬运 App() 中与「任务数据获取」相关的状态、refresh/refreshTasks 与两级轮询 effect。
// 轮询节奏保持原样：无活动任务或打开了详情时 30s；有活动任务时 10s；详情页另有 4s 快轮询。
import { useCallback, useEffect, useState } from 'react'
import { ApiError, getCurrentUser, getSystemStatus, getTask, getTaskPage, setApiUserId, setCsrfCookieName } from '../../../api'
import { ACTIVE_PHASES } from '../../../domain/workflowStates'
import { readStorage } from '../../../safeStorage'
import { settleSessionRefresh } from '../../../sessionRefresh'
import type { AuthUser, SystemStatus, Task } from '../../../types'

export function useTaskPolling(detailId: string | null) {
  const [tasks, setTasks] = useState<Task[]>([])
  const [system, setSystem] = useState<SystemStatus | null>(null)
  const [actor, setActor] = useState<AuthUser | null>(null)
  const [devActorRole, setDevActorRole] = useState<'user' | 'admin'>(() => readStorage('local', 'development-actor-role') === 'admin' ? 'admin' : 'user')
  const [loading, setLoading] = useState(true)
  const [authRequired, setAuthRequired] = useState(false)
  const [error, setError] = useState('')
  const [lastSyncedAt, setLastSyncedAt] = useState<number | null>(null)
  const [nextTaskCursor, setNextTaskCursor] = useState<string | null>(null)
  const [loadingMoreTasks, setLoadingMoreTasks] = useState(false)

  const refreshTasks = useCallback(async () => {
    try {
      const page = await getTaskPage()
      setTasks((current) => {
        const recentIds = new Set(page.items.map((task) => task.id))
        return [...page.items, ...current.filter((task) => !recentIds.has(task.id))]
      })
      setNextTaskCursor(page.nextCursor)
      setLastSyncedAt(Date.now())
      setAuthRequired(false)
      setError('')
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) {
        setActor(null)
        setTasks([])
        setNextTaskCursor(null)
        setAuthRequired(true)
        setError('')
      } else {
        setError(cause instanceof ApiError ? cause.message : '暂时无法连接生产服务')
      }
    }
  }, [])

  const refresh = useCallback(async () => {
    try {
      const status = await getSystemStatus()
      setSystem(status)
      setCsrfCookieName(status.csrfCookieName)
      if (!status.sharedAuthentication) {
        const developmentActorId = devActorRole === 'admin' ? status.phaseOneAdminId : status.phaseOneUserId
        setApiUserId(developmentActorId)
      } else {
        setApiUserId(null)
      }
      const [pageResult, actorResult] = await settleSessionRefresh(getTaskPage(), getCurrentUser())
      if (pageResult.status === 'fulfilled') {
        setTasks(pageResult.value.items)
        setNextTaskCursor(pageResult.value.nextCursor)
        setLastSyncedAt(Date.now())
      }
      if (actorResult.status === 'fulfilled') {
        setActor(actorResult.value)
      }
      const failed = [pageResult, actorResult].find((result) => result.status === 'rejected')
      if (!failed) {
        setAuthRequired(false)
        setError('')
      } else {
        const cause = failed.reason
        setError(cause instanceof ApiError ? cause.message : '暂时无法连接生产服务')
      }
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) {
        setActor(null)
        setTasks([])
        setNextTaskCursor(null)
        setAuthRequired(true)
        setError('')
      } else {
        setError(cause instanceof ApiError ? cause.message : '暂时无法连接生产服务')
      }
    } finally { setLoading(false) }
  }, [devActorRole])

  useEffect(() => {
    const initial = window.setTimeout(() => void refresh(), 0)
    return () => window.clearTimeout(initial)
  }, [refresh])

  useEffect(() => {
    if (!error || authRequired) return
    const retry = window.setInterval(() => void refresh(), 5000)
    return () => window.clearInterval(retry)
  }, [authRequired, error, refresh])

  useEffect(() => {
    if (!actor) return
    let active = true
    let timer: number | undefined
    let inFlight = false
    const hasActiveTasks = tasks.some((task) => ACTIVE_PHASES.has(task.phase))
    const interval = detailId ? 30000 : hasActiveTasks ? 10000 : 30000
    const poll = async () => {
      if (!navigator.onLine || document.visibilityState === 'hidden') {
        if (active) timer = window.setTimeout(() => void poll(), interval)
        return
      }
      if (!active || inFlight) {
        if (active) timer = window.setTimeout(() => void poll(), interval)
        return
      }
      inFlight = true
      try {
        await refreshTasks()
      } finally {
        inFlight = false
        if (active) timer = window.setTimeout(() => void poll(), interval)
      }
    }
    timer = window.setTimeout(() => void poll(), interval)
    return () => {
      active = false
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [actor, detailId, refreshTasks, tasks])

  useEffect(() => {
    const selected = tasks.find((task) => task.id === detailId)
    if (!detailId || !selected || !ACTIVE_PHASES.has(selected.phase)) return
    let active = true
    let timer: number | undefined
    const poll = async () => {
      if (!active) {
        if (active) timer = window.setTimeout(() => void poll(), 4000)
        return
      }
      if (!navigator.onLine || document.visibilityState === 'hidden') {
        timer = window.setTimeout(() => void poll(), 4000)
        return
      }
      try {
        const changed = await getTask(detailId)
        setTasks((current) => current.map((task) => task.id === changed.id ? changed : task))
      } catch {
        // 更慢的任务列表刷新仍是兜底。
      } finally {
        if (active) timer = window.setTimeout(() => void poll(), 4000)
      }
    }
    timer = window.setTimeout(() => void poll(), 4000)
    return () => {
      active = false
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [detailId, tasks])

  return {
    tasks, setTasks,
    system, actor, setActor,
    devActorRole, setDevActorRole,
    loading, setLoading,
    authRequired, setAuthRequired,
    error, setError,
    lastSyncedAt,
    nextTaskCursor, setNextTaskCursor,
    loadingMoreTasks, setLoadingMoreTasks,
    refreshTasks, refresh,
  }
}
