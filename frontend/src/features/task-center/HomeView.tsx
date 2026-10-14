// 本文件由 App.tsx 拆分生成（2026-09-28 前端架构拆分 v2）。
// 代码为逐字搬运，未经逻辑改写。
import { ArrowRight, ChevronRight, Clock3, Film, X } from 'lucide-react'
import { useState } from 'react'
import { type SystemStatus, type Task, type Variant } from '../../types'
import { providerProgress, variantExecutionMessage } from '../../providerPresentation'
import { readJsonStorage, readStorage, writeJsonStorage, writeStorage } from '../../safeStorage'
import { type View } from '../../app/appTypes'
import { ACTIVE_PHASES, AWAITING_USER_INPUT_PHASES, RESULT_PHASES } from '../../domain/workflowStates'
import { TaskElapsed } from '../../shared/components/TaskTiming'
import { EmptyState, SectionHeading } from '../../shared/components/Section'
import { VideoStudio as ProductionComposer } from '../video-studio'
import { ResultCard } from '../production/ResultCard'
import { isAnalysisFailure, taskFailureMessage, taskStatus, variantDisplayName } from '../../domain/taskPresentation'
import { ProviderBadge, TaskStatusBadge } from '../../shared/components/Badges'
import { TaskThumb } from '../../shared/components/Media'
import { type RemixSeed } from '../production/productionTypes'
import { TaskCard } from '../../shared/components/tasks/TaskCard'
import { useOptionalCreativeProject } from '../../creative-project/hooks'
import { prepareDirectorFixedOffline } from '../director-studio/productionBridge'

export const DISMISSED_ATTENTION_STORAGE_KEY = 'dismissed-home-attention'
export const DISMISSED_ATTENTION_ITEMS_STORAGE_KEY = 'dismissed-home-attention-items'

export function ProcessingRow({ task, onOpen }: { task: Task; onOpen: () => void }) {
  const variants = task.variants.filter((item) => ['RUNNING', 'PENDING', 'UNKNOWN'].includes(item.generationStatus))
  const progress = providerProgress(task.phase, task.generationProvider)
  return <button type="button" className="processing-row" onClick={onOpen} aria-label={`查看任务：${task.title}`}>
    <TaskThumb task={task} />
    <span className="processing-main"><span className="processing-main-head"><strong>{task.title}</strong><ProviderBadge provider={task.generationProvider} /><TaskStatusBadge task={task} /></span><span>{progress.label ?? (task.phase === 'GENERATING' ? `正在生成 ${variants.map(variantDisplayName).join('、') || '视频'}` : taskStatus(task).label)}</span></span>
    <span className="progress-cell"><span className="progress-summary"><span>{progress.displayLabel} 进度</span><strong>{progress.percent}%</strong></span><span className={`progress-track ${progress.cssClass}`} aria-label={`${progress.displayLabel} 任务进度 ${progress.percent}%`}><span style={{ width: `${progress.percent}%` }} /></span></span>
    <span className="elapsed"><Clock3 size={14} /><TaskElapsed task={task} /></span>
    <span className="processing-row-action">查看<ChevronRight size={16} /></span>
  </button>
}

export function AttentionItem({ task, onOpen, onDismiss }: { task: Task; onOpen: () => void; onDismiss: () => void }) {
  const unknownVariant = task.variants.find((variant) => variant.generationStatus === 'UNKNOWN')
  const unknown = Boolean(unknownVariant)
  const isWaiting = task.phase === 'AWAITING_CONFIRMATION'
  const isFinalApproval = task.phase === 'AWAITING_FINAL_APPROVAL'
  const reason = task.phase === 'AWAITING_CONFIRMATION'
    ? '等待确认视频动作方案'
    : isFinalApproval
      ? '技术验证已完成，等待人工确认产品保真与关键质量'
    : unknown
      ? variantExecutionMessage(unknownVariant!, task.generationProvider)
      : isAnalysisFailure(task)
        ? taskFailureMessage(task)
        : '视频生成遇到问题，需要处理'
  const action = task.phase === 'AWAITING_CONFIRMATION' ? '立即确认' : isFinalApproval ? '开始人工审核' : unknown ? '查询状态' : isAnalysisFailure(task) ? '重新分析' : '查看原因'
  return <article className="attention-item">
    <button type="button" className="attention-item-dismiss" onClick={onDismiss} aria-label={`关闭“${task.title}”的提醒`} title="关闭此提醒"><X size={16} /></button>
    <TaskThumb task={task} />
    <div className="attention-item-content"><strong title={task.title}>{task.title}</strong><span>{reason} · {isWaiting ? '已等待' : '已用时'} <TaskElapsed task={task} /></span></div>
    <button type="button" className="primary-button" onClick={onOpen}>{action}<ArrowRight size={15} /></button>
  </article>
}

export function HomeView({ active, tasks, seed, system, actorId, onCreated, onOpen, onView, onPlay, onRemix, onFeedbackChanged, canReview = false, cutflowCanWrite = true }: { active: boolean; tasks: Task[]; seed: RemixSeed | null; system: SystemStatus | null; actorId: string | null; onCreated: (task: Task, open?: boolean) => void; onOpen: (task: Task) => void; onView: (view: View) => void; onPlay: (task: Task, variant: Variant) => void; onRemix: (task: Task) => void; onFeedbackChanged: (task: Task) => void; canReview?: boolean; cutflowCanWrite?: boolean }) {
  const projectContext = useOptionalCreativeProject()
  const directorFixedPreparation = prepareDirectorFixedOffline(projectContext?.project ?? null)
  const actionableTasks = tasks.filter((task) => AWAITING_USER_INPUT_PHASES.has(task.phase) || task.variants.some((variant) => variant.generationStatus === 'UNKNOWN'))
  const attentionSignatureFor = (task: Task) => [
    task.phase,
    task.phaseReasonCode ?? '',
    ...task.variants.flatMap((variant) => [variant.kind, variant.generationStatus, variant.errorCode ?? '']),
  ].join(':')
  const [dismissedAttentionItems, setDismissedAttentionItems] = useState<Record<string, string>>(
    () => readJsonStorage<Record<string, string>>('local', DISMISSED_ATTENTION_ITEMS_STORAGE_KEY, {}),
  )
  const needsAction = actionableTasks
    .filter((task) => dismissedAttentionItems[task.id] !== attentionSignatureFor(task))
    .slice(0, 3)
  const background = tasks.filter((task) => ACTIVE_PHASES.has(task.phase) && !needsAction.some((item) => item.id === task.id)).slice(0, Math.max(0, 5 - needsAction.length))
  const results = tasks.filter((task) => RESULT_PHASES.has(task.phase)).flatMap((task) => task.variants.map((variant) => ({ task, variant }))).filter(({ variant }) => variant.downloadArtifactId && variant.generationStatus === 'SUCCEEDED').slice(0, 6)
  const attentionSignature = needsAction.map((task) => `${task.id}:${task.phase}:${task.variants.some((variant) => variant.generationStatus === 'UNKNOWN')}`).sort().join('|')
  const [dismissedAttention, setDismissedAttention] = useState(() => readStorage('session', DISMISSED_ATTENTION_STORAGE_KEY) ?? '')
  const showAttention = Boolean(needsAction.length && attentionSignature !== dismissedAttention)
  const dismissAttention = () => {
    writeStorage('session', DISMISSED_ATTENTION_STORAGE_KEY, attentionSignature)
    setDismissedAttention(attentionSignature)
  }
  const dismissAttentionItem = (task: Task) => {
    setDismissedAttentionItems((current) => {
      const next = { ...current, [task.id]: attentionSignatureFor(task) }
      writeJsonStorage('local', DISMISSED_ATTENTION_ITEMS_STORAGE_KEY, next)
      return next
    })
  }
  return <div className="home-view video-studio" hidden={!active}>
    <div className="home-title"><div><h1>视频工作室</h1><span className="studio-kicker">Video Studio</span></div><div className="home-title-actions"><button className="text-button" onClick={() => onView('records')}>任务中心<ChevronRight size={15} /></button></div></div>
    <div className="home-hero-grid home-hero-grid--full">
      {directorFixedPreparation ? <ProductionComposer key="director-fixed-offline" seed={null} directorFixedPreparation={directorFixedPreparation} onCreated={onCreated} system={system} actorId={actorId} layout="studio" /> : null}
      <ProductionComposer key={seed?.id ?? 'new-production'} seed={seed} onCreated={onCreated} system={system} actorId={actorId} layout="studio" />
    </div>
    {showAttention ? <section className="attention-panel" aria-label="待处理任务">
      <SectionHeading title="需要你操作" count={needsAction.length} action={<div className="attention-panel-actions"><button className="text-button" onClick={() => onView('records')}>查看全部<ChevronRight size={15} /></button><button className="icon-button attention-dismiss" onClick={dismissAttention} aria-label="暂时收起待处理任务" title="暂时收起"><X size={18} /></button></div>} />
      <p>这些是之前创建、目前暂停等待处理的任务，不影响你继续制作新视频。</p>
      <div className="attention-list">{needsAction.map((task) => <AttentionItem key={task.id} task={task} onOpen={() => onOpen(task)} onDismiss={() => dismissAttentionItem(task)} />)}</div>
    </section> : null}
    {background.length ? <section className="home-section background-work"><SectionHeading title="生成队列" count={background.length} action={<button className="text-button" onClick={() => onView('records')}>查看全部<ChevronRight size={15} /></button>} /><div className="studio-task-list" aria-live="polite">{background.map((task) => <TaskCard key={task.id} task={task} onOpen={() => onOpen(task)} />)}</div></section> : null}
    <section className="home-section studio-result-gallery" aria-label="生成结果"><SectionHeading title="生成结果" action={<button className="text-button" onClick={() => onView('records')}>查看全部记录<ChevronRight size={15} /></button>} />{results.length ? <div className="results-grid">{results.map(({ task, variant }) => <ResultCard key={variant.id} task={task} variant={variant} onPlay={() => onPlay(task, variant)} onRemix={() => onRemix(task)} onOpen={() => onOpen(task)} onFeedbackChanged={onFeedbackChanged} canReview={canReview} cutflowEnabled={system?.cutflowHandoffEnabled} cutflowCanWrite={cutflowCanWrite} />)}</div> : <EmptyState icon={<Film size={24} />} title="还没有生成结果" description="" />}</section>
  </div>
}
