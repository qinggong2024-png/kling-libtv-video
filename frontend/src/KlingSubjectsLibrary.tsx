import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  ImageIcon,
  LoaderCircle,
  RefreshCw,
  Search,
  Trash2,
  UsersRound,
  XCircle,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { ApiError, deleteKlingElement, getKlingElements } from './api'
import {
  getKlingElementStatusGroup,
  getKlingElementStatusLabel,
} from './klingElementStatus'
import type { KlingElement } from './types'

type SubjectFilter = 'all' | 'processing' | 'available' | 'failed'
type SubjectSource = 'custom' | 'official'
type SubjectSourceFilter = 'all' | SubjectSource

interface SourcedKlingElement extends KlingElement {
  source: SubjectSource
}

interface KlingSubjectsLibraryProps {
  actorId: string | null
  canDelete: boolean
}

const FILTERS: ReadonlyArray<{ value: SubjectFilter; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'processing', label: '处理中' },
  { value: 'available', label: '可用' },
  { value: 'failed', label: '失败' },
]

const SOURCE_FILTERS: ReadonlyArray<{ value: SubjectSourceFilter; label: string }> = [
  { value: 'all', label: '全部来源' },
  { value: 'custom', label: '自定义主体' },
  { value: 'official', label: '官方预置' },
]

function formatUpdatedAt(value: string | null): string {
  if (!value) return '更新时间未知'
  const timestamp = Date.parse(value)
  if (Number.isNaN(timestamp)) return value
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(timestamp)
}

function errorMessage(cause: unknown, fallback: string): string {
  return cause instanceof ApiError ? cause.message : fallback
}

export function KlingSubjectsLibrary({ actorId, canDelete }: KlingSubjectsLibraryProps) {
  const [customElements, setCustomElements] = useState<SourcedKlingElement[]>([])
  const [officialElements, setOfficialElements] = useState<SourcedKlingElement[]>([])
  const [customTotal, setCustomTotal] = useState(0)
  const [officialTotal, setOfficialTotal] = useState(0)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<SubjectFilter>('all')
  const [sourceFilter, setSourceFilter] = useState<SubjectSourceFilter>('all')
  const [loading, setLoading] = useState(true)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const requestControllerRef = useRef<AbortController | null>(null)

  const load = useCallback(async () => {
    requestControllerRef.current?.abort()
    const controller = new AbortController()
    requestControllerRef.current = controller
    setLoading(true)
    setError('')
    setNotice('')

    try {
      const [customResult, officialResult] = await Promise.allSettled([
        getKlingElements(actorId, 1, 100, false, controller.signal),
        getKlingElements(actorId, 1, 100, true, controller.signal),
      ])
      if (controller.signal.aborted) return

      if (customResult.status === 'fulfilled') {
        setCustomElements(customResult.value.items.map((element) => ({ ...element, source: 'custom' })))
        setCustomTotal(customResult.value.total)
      }
      if (officialResult.status === 'fulfilled') {
        setOfficialElements(officialResult.value.items.map((element) => ({ ...element, source: 'official' })))
        setOfficialTotal(officialResult.value.total)
      }

      const failures = [
        customResult.status === 'rejected'
          ? errorMessage(customResult.reason, '自定义主体读取失败')
          : '',
        officialResult.status === 'rejected'
          ? errorMessage(officialResult.reason, '官方预置主体读取失败')
          : '',
      ].filter(Boolean)
      setError(failures.length ? `${failures.join('；')}。` : '')
    } finally {
      if (requestControllerRef.current === controller) {
        requestControllerRef.current = null
        setLoading(false)
      }
    }
  }, [actorId])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => {
      window.clearTimeout(timer)
      requestControllerRef.current?.abort()
      requestControllerRef.current = null
    }
  }, [load])

  const elements = useMemo(
    () => [...customElements, ...officialElements],
    [customElements, officialElements],
  )
  const total = customTotal + officialTotal

  const visibleElements = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase('zh-CN')
    return elements.filter((element) => {
      if (sourceFilter !== 'all' && element.source !== sourceFilter) return false
      if (filter !== 'all' && getKlingElementStatusGroup(element.status) !== filter) return false
      if (!normalizedQuery) return true
      const searchable = [
        element.name,
        element.description,
        element.id,
        element.status,
      ].filter(Boolean).join(' ').toLocaleLowerCase('zh-CN')
      return searchable.includes(normalizedQuery)
    })
  }, [elements, filter, query, sourceFilter])

  const remove = async (element: SourcedKlingElement) => {
    if (!canDelete || element.source !== 'custom' || element.raw?.localJob || deletingId) return
    const displayName = element.name?.trim() || element.id
    if (!window.confirm(`确定删除主体“${displayName}”吗？此操作无法撤销。`)) return

    setDeletingId(element.id)
    setError('')
    setNotice('')
    try {
      await deleteKlingElement(actorId, element.id)
      setCustomElements((current) => current.filter((item) => item.id !== element.id))
      setCustomTotal((current) => Math.max(0, current - 1))
      setNotice(`主体“${displayName}”已删除。`)
    } catch (cause) {
      setError(errorMessage(cause, '删除主体失败，请稍后重试。'))
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <section className="kling-subject-library" aria-labelledby="kling-subject-library-title">
      <header className="kling-subject-library-header">
        <div className="kling-subject-library-heading">
          <span className="kling-subject-library-eyebrow">内容库</span>
          <h2 id="kling-subject-library-title">历史主体</h2>
          <p>查找和管理已上传到可灵的商品或人物主体。</p>
        </div>
        <button
          className="kling-subject-library-refresh"
          type="button"
          disabled={loading}
          onClick={() => void load()}
        >
          <RefreshCw
            aria-hidden="true"
            className={loading ? 'kling-subject-library-icon--spinning' : undefined}
            size={16}
          />
          {loading ? '刷新中' : '刷新'}
        </button>
      </header>

      <div className="kling-subject-library-toolbar">
        <label className="kling-subject-library-search">
          <span className="kling-subject-library-visually-hidden">搜索历史主体</span>
          <Search aria-hidden="true" size={17} />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索名称、描述或主体 ID"
          />
        </label>

        <div>
          <div className="kling-subject-library-filters" role="group" aria-label="按主体来源筛选">
            {SOURCE_FILTERS.map((item) => (
              <button
                key={item.value}
                className={`kling-subject-library-filter${sourceFilter === item.value ? ' kling-subject-library-filter--active' : ''}`}
                type="button"
                aria-pressed={sourceFilter === item.value}
                onClick={() => setSourceFilter(item.value)}
              >
                {item.label}
              </button>
            ))}
          </div>
          <div className="kling-subject-library-filters" role="group" aria-label="按主体状态筛选">
            {FILTERS.map((item) => (
              <button
                key={item.value}
                className={`kling-subject-library-filter${filter === item.value ? ' kling-subject-library-filter--active' : ''}`}
                type="button"
                aria-pressed={filter === item.value}
                onClick={() => setFilter(item.value)}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="kling-subject-library-summary" aria-live="polite">
        <span>共 {total} 个主体（自定义 {customTotal} · 官方预置 {officialTotal}）</span>
        {query || filter !== 'all' || sourceFilter !== 'all'
          ? <span>当前显示 {visibleElements.length} 个</span>
          : null}
      </div>

      {error ? (
        <div className="kling-subject-library-alert kling-subject-library-alert--error" role="alert">
          <AlertTriangle aria-hidden="true" size={17} />
          <span>{error}</span>
        </div>
      ) : null}
      {notice ? (
        <div className="kling-subject-library-alert kling-subject-library-alert--success" role="status">
          <CheckCircle2 aria-hidden="true" size={17} />
          <span>{notice}</span>
        </div>
      ) : null}

      {loading && elements.length === 0 ? (
        <div className="kling-subject-library-state" role="status">
          <LoaderCircle
            aria-hidden="true"
            className="kling-subject-library-icon--spinning"
            size={22}
          />
          <strong>正在读取历史主体</strong>
          <span>请稍候</span>
        </div>
      ) : visibleElements.length > 0 ? (
        <div className="kling-subject-library-grid">
          {visibleElements.map((element) => {
            const group = getKlingElementStatusGroup(element.status)
            const referenceCount = element.imageUrls.length
            const thumbnailUrl = element.imageUrls[0]
            const displayName = element.name?.trim() || '未命名主体'
            const isDeleting = deletingId === element.id
            const localFailure = element.raw?.localJob && group === 'failed'
              ? element.raw.errorMessage?.trim()
              : ''

            return (
              <article className="kling-subject-library-card" key={`${element.source}:${element.id}`}>
                <div className="kling-subject-library-thumbnail">
                  {thumbnailUrl ? (
                    <img src={thumbnailUrl} alt={`${displayName}的主体参考图`} loading="lazy" />
                  ) : (
                    <ImageIcon aria-hidden="true" size={28} />
                  )}
                </div>

                <div className="kling-subject-library-card-body">
                  <div className="kling-subject-library-card-heading">
                    <h3>{displayName}</h3>
                    <span
                      className={`kling-subject-library-status kling-subject-library-status--${group}`}
                      title={`可灵状态：${element.status}`}
                    >
                      {group === 'available' ? <CheckCircle2 aria-hidden="true" size={14} /> : null}
                      {group === 'failed' ? <XCircle aria-hidden="true" size={14} /> : null}
                      {group === 'processing' ? <Clock3 aria-hidden="true" size={14} /> : null}
                      {getKlingElementStatusLabel(element.status)}
                    </span>
                  </div>

                  <p className="kling-subject-library-description">
                    {localFailure || element.description?.trim() || '暂无主体描述'}
                  </p>

                  <dl className="kling-subject-library-meta">
                    <div>
                      <dt>参考素材</dt>
                      <dd>{referenceCount > 0 ? `${referenceCount} 张图片` : element.videoUrl ? '1 个视频' : '暂无'}</dd>
                    </div>
                    <div>
                      <dt>更新时间</dt>
                      <dd>{formatUpdatedAt(element.updatedAt ?? element.createdAt)}</dd>
                    </div>
                  </dl>

                  <div className="kling-subject-library-card-footer">
                    <span className="kling-subject-library-id" title={element.id}>
                      {element.source === 'official' ? '官方预置' : '自定义'} · {element.id}
                    </span>
                    {canDelete && element.source === 'custom' && !element.raw?.localJob ? (
                      <button
                        className="kling-subject-library-delete"
                        type="button"
                        disabled={deletingId !== null}
                        aria-label={`删除主体 ${displayName}`}
                        onClick={() => void remove(element)}
                      >
                        {isDeleting ? (
                          <LoaderCircle
                            aria-hidden="true"
                            className="kling-subject-library-icon--spinning"
                            size={16}
                          />
                        ) : (
                          <Trash2 aria-hidden="true" size={16} />
                        )}
                        {isDeleting ? '删除中' : '删除'}
                      </button>
                    ) : null}
                  </div>
                </div>
              </article>
            )
          })}
        </div>
      ) : (
        <div className="kling-subject-library-state">
          <UsersRound aria-hidden="true" size={26} />
          <strong>{elements.length === 0 ? '还没有历史主体' : '没有符合条件的主体'}</strong>
          <span>
            {elements.length === 0
              ? '在制作页上传主体图后，创建成功的主体会出现在这里。'
              : '请尝试更换关键词或状态筛选。'}
          </span>
        </div>
      )}
    </section>
  )
}
