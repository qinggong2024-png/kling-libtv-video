// 本文件由 App.tsx 拆分生成（2026-09-21 前端架构拆分 v1）。
// readAppLocation 为逐字搬运；useAppNavigation 把 view/detailId/adminSection
// 三个状态、popstate 监听与 navigate 收敛到一处，App 不再自己管路由。
import { useCallback, useEffect, useState } from 'react'
import type { AdminSection, RecordsFilter, View } from './appTypes'
import { readJsonStorage, removeStorage, writeJsonStorage } from '../safeStorage'

const RECORD_FILTERS: RecordsFilter[] = ['all', 'attention', 'active', 'partial', 'done', 'failed', 'cancelled']
const RECORDS_RETURN_KEY = 'app.records-return'
type RecordsReturnSnapshot = { url: string; scrollY: number }

function readAppLocationFromSearch(search: string): { view: View; detailId: string | null; adminSection: AdminSection; recordsFilter: RecordsFilter; recordsQuery: string } {
  const params = new URLSearchParams(search)
  const requestedView = params.get('view')
  const view: View = requestedView === 'images' || requestedView === 'records' || requestedView === 'library' || requestedView === 'admin' || requestedView === 'settings' ? requestedView : 'make'
  const requestedAdminSection = params.get('section')
  const adminSection: AdminSection = requestedAdminSection === 'accounts' || requestedAdminSection === 'providers' || requestedAdminSection === 'security'
    ? requestedAdminSection
    : 'overview'
  const requestedFilter = params.get('filter') as RecordsFilter | null
  const recordsFilter = view === 'records' && requestedFilter && RECORD_FILTERS.includes(requestedFilter) ? requestedFilter : 'all'
  const recordsQuery = view === 'records' ? (params.get('q') ?? '') : ''
  return { view, detailId: view === 'make' ? params.get('task') : null, adminSection, recordsFilter, recordsQuery }
}

export function readAppLocation() {
  return readAppLocationFromSearch(window.location.search)
}

export function useAppNavigation() {
  const [view, setView] = useState<View>(() => readAppLocation().view)
  const [detailId, setDetailId] = useState<string | null>(() => readAppLocation().detailId)
  const [adminSection, setAdminSection] = useState<AdminSection>(() => readAppLocation().adminSection)
  const [recordsFilter, setRecordsFilter] = useState<RecordsFilter>(() => readAppLocation().recordsFilter)
  const [recordsQuery, setRecordsQuery] = useState(() => readAppLocation().recordsQuery)
  const [recordsRestoreScroll, setRecordsRestoreScroll] = useState<number | null>(null)

  useEffect(() => {
    const restoreLocation = () => {
      const next = readAppLocation()
      setView(next.view)
      setDetailId(next.detailId)
      setAdminSection(next.adminSection)
      setRecordsFilter(next.recordsFilter)
      setRecordsQuery(next.recordsQuery)
    }
    window.addEventListener('popstate', restoreLocation)
    return () => window.removeEventListener('popstate', restoreLocation)
  }, [])

  const navigateRecords = useCallback((nextFilter: RecordsFilter, nextQuery: string, replace = false) => {
    removeStorage('session', RECORDS_RETURN_KEY)
    const normalizedQuery = nextQuery.trim()
    setView('records')
    setDetailId(null)
    setRecordsFilter(nextFilter)
    setRecordsQuery(normalizedQuery)
    const params = new URLSearchParams({ view: 'records' })
    if (nextFilter !== 'all') params.set('filter', nextFilter)
    if (normalizedQuery) params.set('q', normalizedQuery)
    const url = `${window.location.pathname}?${params.toString()}`
    window.history[replace ? 'replaceState' : 'pushState'](null, '', url)
  }, [])

  const openTaskFromRecords = useCallback((taskId: string) => {
    writeJsonStorage('session', RECORDS_RETURN_KEY, { url: window.location.href, scrollY: window.scrollY })
    const params = new URLSearchParams({ task: taskId })
    setView('make')
    setDetailId(taskId)
    window.history.pushState(null, '', `${window.location.pathname}?${params.toString()}`)
  }, [])

  const closeTaskDetail = useCallback(() => {
    const snapshot = readJsonStorage<RecordsReturnSnapshot | null>('session', RECORDS_RETURN_KEY, null)
    const snapshotUrl = snapshot?.url ? new URL(snapshot.url, window.location.href) : null
    if (!snapshotUrl || snapshotUrl.searchParams.get('view') !== 'records') {
      removeStorage('session', RECORDS_RETURN_KEY)
      setView('make')
      setDetailId(null)
      window.history.pushState(null, '', window.location.pathname)
      return
    }
    removeStorage('session', RECORDS_RETURN_KEY)
    const next = snapshotUrl
    const location = readAppLocationFromSearch(next.search)
    setView(location.view)
    setDetailId(location.detailId)
    setAdminSection(location.adminSection)
    setRecordsFilter(location.recordsFilter)
    setRecordsQuery(location.recordsQuery)
    setRecordsRestoreScroll(snapshot?.scrollY ?? 0)
    window.history.replaceState(null, '', `${next.pathname}${next.search}${next.hash}`)
  }, [])

  const navigate = useCallback((nextView: View, nextDetailId: string | null = null, replace = false, nextAdminSection: AdminSection = 'overview') => {
    setView(nextView)
    setDetailId(nextView === 'make' ? nextDetailId : null)
    if (nextView === 'records') {
      removeStorage('session', RECORDS_RETURN_KEY)
      setRecordsFilter('all')
      setRecordsQuery('')
    }
    if (nextView === 'admin') setAdminSection(nextAdminSection)
    const params = new URLSearchParams()
    if (nextView !== 'make') params.set('view', nextView)
    if (nextView === 'make' && nextDetailId) params.set('task', nextDetailId)
    if (nextView === 'admin' && nextAdminSection !== 'overview') params.set('section', nextAdminSection)
    const url = `${window.location.pathname}${params.size ? `?${params.toString()}` : ''}`
    window.history[replace ? 'replaceState' : 'pushState'](null, '', url)
  }, [])

  return { view, detailId, adminSection, recordsFilter, recordsQuery, recordsRestoreScroll, setRecordsRestoreScroll, navigate, navigateRecords, openTaskFromRecords, closeTaskDetail, setAdminSection }
}
