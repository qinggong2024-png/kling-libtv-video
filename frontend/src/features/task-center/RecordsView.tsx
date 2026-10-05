// 本文件由 App.tsx 拆分生成（2026-09-28 前端架构拆分 v2）。
// 代码为逐字搬运，未经逻辑改写。
import { ChevronRight, ListVideo, LoaderCircle, Search, X } from 'lucide-react'
import { useState } from 'react'
import { type Task, type Variant } from '../../types'
import { ACTIVE_PHASES, COMPLETED_PHASES, FAILED_PHASES } from '../../domain/workflowStates'
import { EmptyState, SectionHeading } from '../../shared/components/Section'
import { ResultCard } from '../production/ResultCard'
import { formatTime, isAnalysisFailure, taskFailureMessage, variantDisplayName, variantShortLabel } from '../../domain/taskPresentation'
import { TaskStatusBadge } from '../../shared/components/Badges'
import { TaskThumb } from '../../shared/components/Media'

export type RecordFilter = 'all' | 'attention' | 'active' | 'partial' | 'done' | 'failed' | 'cancelled'
export function RecordsView({ tasks, hasMore, loadingMore, onLoadMore, onOpen, onPlay, onRemix, onFeedbackChanged, onCreateTask }: { tasks: Task[]; hasMore: boolean; loadingMore: boolean; onLoadMore: () => void; onOpen: (task: Task) => void; onPlay: (task: Task, variant: Variant) => void; onRemix: (task: Task) => void; onFeedbackChanged: (task: Task) => void; onCreateTask: () => void }) {
  const [filter, setFilter] = useState<RecordFilter>('all')
  const [query, setQuery] = useState('')
  const groups: Array<{ value: RecordFilter; label: string; test: (task: Task) => boolean }> = [
    { value: 'all', label: '全部', test: () => true },
    { value: 'attention', label: '需要处理', test: (task) => task.phase === 'AWAITING_CONFIRMATION' || task.phase === 'ACTION_REQUIRED' },
    { value: 'active', label: '处理中', test: (task) => ACTIVE_PHASES.has(task.phase) },
    { value: 'partial', label: '部分完成', test: (task) => task.phase === 'PARTIALLY_DELIVERABLE' },
    { value: 'done', label: '已完成', test: (task) => COMPLETED_PHASES.has(task.phase) },
    { value: 'failed', label: '失败', test: (task) => FAILED_PHASES.has(task.phase) },
    { value: 'cancelled', label: '已取消', test: (task) => task.phase === 'CANCELLED' },
  ]
  const group = groups.find((item) => item.value === filter)!
  const keyword = query.trim().toLowerCase()
  const searching = keyword.length > 0
  const matchesQuery = (task: Task) => !searching || task.title.toLowerCase().includes(keyword)
  const visible = tasks.filter((task) => group.test(task) && matchesQuery(task))
  const completed = visible.filter((task) => COMPLETED_PHASES.has(task.phase))
  const listRows = filter === 'done' ? [] : visible.filter((task) => !COMPLETED_PHASES.has(task.phase))
  const completedResults = completed
    .flatMap((task) => task.variants.map((variant) => ({ task, variant })))
    .filter(({ variant }) => variant.downloadArtifactId)
    .sort((left, right) => Date.parse(right.task.updatedAt) - Date.parse(left.task.updatedAt))
  const displayedCompletedResults = filter === 'all' ? completedResults.slice(0, 3) : completedResults
  // 计数必须与列表同口径：搜索激活时给出匹配数，否则会出现「卡片 17 条 / 列表没有记录」的矛盾。
  const countOf = (test: (task: Task) => boolean) => (searching ? tasks.filter(test).filter(matchesQuery).length : tasks.filter(test).length)
  const attentionCount = countOf((task) => task.phase === 'AWAITING_CONFIRMATION' || task.phase === 'ACTION_REQUIRED')
  const activeCount = countOf((task) => ACTIVE_PHASES.has(task.phase))
  const doneCount = countOf((task) => COMPLETED_PHASES.has(task.phase))
  const allCount = countOf(() => true)
  return <div className="page-view"><div className="page-title"><div><span>Production Tasks</span><h1>任务</h1><p>查找任务、继续处理，或直接播放和下载已完成视频。</p></div><label className="search-field"><Search size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索任务名称" aria-label="搜索任务名称" />{searching ? <button type="button" className="search-field-clear" onClick={(event) => { event.preventDefault(); setQuery('') }} aria-label="清除搜索关键词" title="清除搜索"><X size={15} /></button> : null}</label></div>
    {searching ? <div className="filter-notice" role="status"><Search size={15} /><span>正在按「{query.trim()}」筛选，下方数量与列表均为匹配结果（共 {tasks.length} 条任务）。</span><button type="button" className="text-button" onClick={() => setQuery('')}>清除搜索</button></div> : null}
    <section className="records-overview" aria-label="任务概览">
      <button type="button" className={filter === 'all' ? 'is-active' : ''} aria-pressed={filter === 'all'} onClick={() => setFilter('all')}><span className="records-overview-dot is-blue" /><span><small>全部任务</small><strong>{allCount}</strong></span></button>
      <button type="button" className={filter === 'attention' ? 'is-active' : ''} aria-pressed={filter === 'attention'} onClick={() => setFilter('attention')}><span className="records-overview-dot is-amber" /><span><small>需要处理</small><strong>{attentionCount}</strong></span></button>
      <button type="button" className={filter === 'active' ? 'is-active' : ''} aria-pressed={filter === 'active'} onClick={() => setFilter('active')}><span className="records-overview-dot is-purple" /><span><small>生产中</small><strong>{activeCount}</strong></span></button>
      <button type="button" className={filter === 'done' ? 'is-active' : ''} aria-pressed={filter === 'done'} onClick={() => setFilter('done')}><span className="records-overview-dot is-green" /><span><small>已完成</small><strong>{doneCount}</strong></span></button>
    </section>
    <div className="filter-tabs">{groups.map((item) => { const count = countOf(item.test); return <button key={item.value} className={filter === item.value ? 'is-active' : ''} onClick={() => setFilter(item.value)}>{item.label}<span>{count}</span></button> })}</div>
    {displayedCompletedResults.length ? <section className={`records-completed${filter === 'all' ? ' records-completed--preview' : ''}`} aria-label={filter === 'all' ? '最近完成的视频' : '全部已完成视频'}><SectionHeading title={filter === 'all' ? '最近完成' : '视频结果'} count={displayedCompletedResults.length} action={filter === 'all' ? <button type="button" className="text-button" onClick={() => setFilter('done')}>查看全部已完成<ChevronRight size={15} /></button> : undefined} /><div className="results-grid results-grid--library">{displayedCompletedResults.map(({ task, variant }) => <ResultCard key={variant.id} task={task} variant={variant} onPlay={() => onPlay(task, variant)} onRemix={() => onRemix(task)} onOpen={() => onOpen(task)} onFeedbackChanged={onFeedbackChanged} />)}</div></section> : null}
    {listRows.length ? <div className="task-table"><div className="task-table-head"><span>产品 / 任务</span><span>当前状态</span><span>结果进度</span><span>更新时间</span><span /></div>{listRows.map((task) => <button className="task-table-row" key={task.id} onClick={() => onOpen(task)}><span className="task-name-cell"><TaskThumb task={task} /><span><strong>{task.title}</strong><small>{task.assetCount} 张素材</small></span></span><span><TaskStatusBadge task={task} />{task.phaseReasonCode ? <small>{isAnalysisFailure(task) ? taskFailureMessage(task) : task.phaseReasonCode}</small> : null}</span><span className="mini-variants">{task.variants.map((variant) => <i key={variant.id} className={variant.generationStatus === 'FAILED' ? 'is-failed' : variant.generationStatus === 'SUCCEEDED' ? 'is-done' : ''} aria-label={variantDisplayName(variant)} title={variantDisplayName(variant)}>{variantShortLabel(variant)}</i>)}</span><span>{formatTime(task.updatedAt)}</span><span><ChevronRight size={17} /></span></button>)}</div> : null}
    {hasMore ? <div className="records-load-more"><button className="secondary-button" disabled={loadingMore} onClick={onLoadMore}>{loadingMore ? <LoaderCircle className="spin" size={16} /> : null}{loadingMore ? '正在加载' : '加载更早记录'}</button></div> : null}
    {!visible.length ? (searching
      ? <EmptyState icon={<Search size={24} />} title={`没有匹配“${query.trim()}”的任务`} description="换个关键词再试，或清除搜索查看全部任务。" action={<button type="button" className="secondary-button" onClick={() => setQuery('')}>清除搜索</button>} />
      : tasks.length
        ? <EmptyState icon={<ListVideo size={24} />} title={group.label === '全部' ? '还没有任务' : `“${group.label}”下暂无任务`} description={group.label === '全部' ? '在「视频制作」上传素材即可创建第一条任务。' : '任务状态变化后会自动归入对应分类。'} action={group.label === '全部' ? <button type="button" className="primary-button" onClick={onCreateTask}>去创建任务</button> : <button type="button" className="secondary-button" onClick={() => setFilter('all')}>查看全部任务</button>} />
        : <EmptyState icon={<ListVideo size={24} />} title="还没有任务" description="在「视频制作」上传素材，创建你的第一条服装广告视频。" action={<button type="button" className="primary-button" onClick={onCreateTask}>去创建任务</button>} />
    ) : null}
  </div>
}
