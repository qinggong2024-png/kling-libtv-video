// 本文件由 App.tsx 拆分生成（2026-09-28 前端架构拆分 v2）。
// 代码为逐字搬运，未经逻辑改写。
import { AlertTriangle, Check, LoaderCircle } from 'lucide-react'
import { useEffect, useState } from 'react'
import { type Task } from '../../types'
import { formatDurationSeconds, formatElapsed, parseTaskTimestamp, visibleTaskTimingStageKeys } from '../../taskTiming'
import { providerTimingStageLabel } from '../../providerPresentation'
import { COMPLETED_PHASES, SETTLED_PHASES } from '../../domain/workflowStates'
import { taskStatus } from '../../domain/taskPresentation'

export function TaskElapsed({ task }: { task: Pick<Task, 'phase' | 'createdAt' | 'updatedAt'> }) {
  const isTerminal = SETTLED_PHASES.has(task.phase)
  const [now, setNow] = useState(Date.now)
  useEffect(() => {
    if (isTerminal) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [isTerminal])
  return <>{formatElapsed(task.createdAt, isTerminal ? task.updatedAt : now)}</>
}

export type TaskTimingStage = NonNullable<Task['timing']>['stages'][number]

const TASK_TIMING_STAGE_META: Array<{
  key: TaskTimingStage['key']
  category: 'system' | 'user'
}> = [
  { key: 'SOURCE_UPLOAD', category: 'system' },
  { key: 'ANALYSIS', category: 'system' },
  { key: 'CONFIRMATION', category: 'user' },
  { key: 'MATERIALIZATION', category: 'system' },
  { key: 'GENERATION', category: 'system' },
  { key: 'DOWNLOAD', category: 'system' },
]

function taskTimingStageShortLabel(key: TaskTimingStage['key']): string {
  if (key === 'SOURCE_UPLOAD') return '素材'
  if (key === 'ANALYSIS') return '分析'
  if (key === 'CONFIRMATION') return '确认'
  if (key === 'MATERIALIZATION') return '上传'
  if (key === 'GENERATION') return '生成'
  return '下载'
}

function formatCompactDurationSeconds(value: number): string {
  const seconds = Math.max(0, Math.floor(value))
  if (seconds < 60) return `${seconds}秒`
  if (seconds < 3600) {
    const minutes = Math.floor(seconds / 60)
    const remainder = seconds % 60
    return remainder ? `${minutes}分${remainder}秒` : `${minutes}分钟`
  }
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  return minutes ? `${hours}时${minutes}分` : `${hours}小时`
}

function stageElapsedSeconds(stage: TaskTimingStage, now: number): number | null {
  const recorded = stage.durationSeconds ?? 0
  if (stage.status !== 'ACTIVE' || !stage.activeStartedAt) {
    return stage.durationSeconds
  }
  const live = Math.max(0, (now - parseTaskTimestamp(stage.activeStartedAt)) / 1000)
  return stage.key === 'ANALYSIS' ? recorded + live : live
}

export function TaskTimingTimeline({ task }: { task: Task }) {
  const stagesByKey = new Map((task.timing?.stages ?? []).map((stage) => [stage.key, stage]))
  const hasActiveStage = task.timing?.stages.some((stage) => stage.status === 'ACTIVE') ?? false
  const [now, setNow] = useState(Date.now)
  useEffect(() => {
    if (!hasActiveStage) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [hasActiveStage])

  const visibleStageKeys = new Set(visibleTaskTimingStageKeys(task.workflowKind))
  const stages = TASK_TIMING_STAGE_META.filter(({ key }) => visibleStageKeys.has(key)).map((meta) => ({
    ...meta,
    stage: stagesByKey.get(meta.key) ?? {
      key: meta.key,
      status: 'PENDING' as const,
      durationSeconds: null,
      activeStartedAt: null,
      attemptCount: null,
    },
  }))
  const activeStage = stages.find(({ stage }) => stage.status === 'ACTIVE')
  const sourceUploadSeconds = stagesByKey.get('SOURCE_UPLOAD')?.durationSeconds ?? 0
  const taskEnd = SETTLED_PHASES.has(task.phase) ? parseTaskTimestamp(task.updatedAt) : now
  // 注意：这是「墙钟时长」（创建至今），包含人工等待，不是系统处理耗时。
  const taskAgeSeconds = sourceUploadSeconds + Math.max(0, (taskEnd - parseTaskTimestamp(task.createdAt)) / 1000)
  const systemSeconds = stages.reduce((total, item) => {
    if (item.category !== 'system') return total
    return total + (stageElapsedSeconds(item.stage, now) ?? 0)
  }, 0)
  // 方案确认阶段只存在于 legacy 分析流程；固定模板任务上渲染「0 秒」会和「正在等待最终审核」互相矛盾。
  const confirmationVisible = stages.some(({ key }) => key === 'CONFIRMATION')
  const confirmationStage = confirmationVisible ? stagesByKey.get('CONFIRMATION') : undefined
  const confirmationSeconds = confirmationStage ? stageElapsedSeconds(confirmationStage, now) ?? 0 : 0

  return <section className="task-timing" aria-labelledby="task-timing-title">
    <header className="task-timing-header">
      <div>
        <span>{activeStage ? '当前阶段' : COMPLETED_PHASES.has(task.phase) ? '任务已完成' : task.phase === 'PARTIALLY_DELIVERABLE' ? '部分结果已就绪' : '执行状态'}</span>
        <h3 id="task-timing-title">
          {activeStage ? providerTimingStageLabel(activeStage.key, task.generationProvider) : taskStatus(task).label}
        </h3>
        {activeStage ? <p aria-live="polite">已进行 {formatDurationSeconds(stageElapsedSeconds(activeStage.stage, now) ?? 0)}</p> : null}
      </div>
      <dl className="task-timing-summary" aria-label="任务耗时汇总">
        <div title="系统实际执行各阶段所花时间之和，不含人工等待"><dt>系统处理</dt><dd>{systemSeconds > 0 ? formatDurationSeconds(systemSeconds) : '暂无记录'}</dd></div>
        {confirmationVisible ? <div title="等待确认视频动作方案的累计时长"><dt>等待方案确认</dt><dd>{formatDurationSeconds(confirmationSeconds)}</dd></div> : null}
        <div title="从任务创建至今的墙钟时长，包含人工等待，不等于系统处理耗时"><dt>任务年龄</dt><dd>{formatDurationSeconds(taskAgeSeconds)}</dd></div>
      </dl>
    </header>
    <ol
      className="task-timing-stages"
      style={{ gridTemplateColumns: `repeat(${stages.length}, minmax(0, 1fr))` }}
    >
      {stages.map(({ key, category, stage }, index) => {
        const elapsed = stageElapsedSeconds(stage, now)
        const statusText = stage.status === 'ACTIVE'
          ? formatCompactDurationSeconds(elapsed ?? 0)
          : stage.status === 'COMPLETED'
            ? elapsed === null ? '已完成' : formatCompactDurationSeconds(elapsed)
            : stage.status === 'FAILED' ? '未完成' : '待执行'
        const fullLabel = providerTimingStageLabel(key, task.generationProvider)
        return <li key={key} className={`task-timing-stage is-${stage.status.toLowerCase()}`} aria-label={`${fullLabel}，${category === 'user' ? '用户等待' : '系统处理'}，${statusText}`} aria-current={stage.status === 'ACTIVE' ? 'step' : undefined}>
          <span className="task-timing-marker" aria-hidden="true">
            {stage.status === 'COMPLETED' ? <Check size={15} /> : stage.status === 'ACTIVE' ? <LoaderCircle className="spin" size={15} /> : stage.status === 'FAILED' ? <AlertTriangle size={15} /> : index + 1}
          </span>
          <span className="task-timing-copy">
            <strong><span className="task-timing-label-full">{fullLabel}</span><span className="task-timing-label-short">{taskTimingStageShortLabel(key)}</span></strong>
            <small>{category === 'user' ? '用户等待' : '系统处理'}{stage.attemptCount && stage.attemptCount > 1 ? ` · 共 ${stage.attemptCount} 次` : ''}</small>
          </span>
          <span className="task-timing-duration">{statusText}</span>
        </li>
      })}
    </ol>
  </section>
}
