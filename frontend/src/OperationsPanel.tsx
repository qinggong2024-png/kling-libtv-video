import { Activity, AlertTriangle, CircleDollarSign, Gauge, Layers3, LoaderCircle, Pause, Play, RefreshCw, Server, Timer, WalletCards, Workflow } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { ApiError, getOperations, setOperationalPause } from './api'
import type { OperationsSnapshot } from './types'

const runnerStatusLabels: Record<string, string> = {
  ONLINE: '在线',
  WARNING: '异常',
  PAUSED: '已暂停',
  OFFLINE: '离线',
}

const alertCodeLabels: Record<string, string> = {
  LIBTV_AUTH_REQUIRED: 'LibTV 需要重新登录',
  UNKNOWN_THRESHOLD_EXCEEDED: '未知任务比例超过阈值',
  PREPARED_QUEUE_BELOW_LOW_WATERMARK: '待生成队列低于最低水位',
}

const alertActionLabels: Record<string, string> = {
  RUN_REFRESH_LIBTV_LOGIN: '请刷新 LibTV 登录状态',
  PAUSE_NEW_PAID_SUBMISSIONS: '请暂停新的付费任务',
  OBSERVE_MATERIALIZATION_CAPACITY: '请检查任务准备能力',
}

const stageLabels: Record<string, string> = {
  analysis: '图片分析',
  confirmation: '人工确认',
  materialization: '远程准备',
  queue: '队列等待',
  generation: '视频生成',
  delivery: '下载校验',
  endToEnd: '端到端',
}

const constraintLabels: Record<string, string> = {
  GLOBAL_PAUSED: '任务调度已暂停',
  GENERATION_CAPACITY: '生成槽位已满',
  RUNNER_DISPATCH: '运行器派发',
  CONFIRMATION: '等待人工确认',
  MATERIALIZATION: '远程准备',
  ANALYSIS: '图片分析',
  DELIVERY: '下载与校验',
  IDLE: '当前无积压',
}

function formatDuration(seconds: number | null): string {
  if (seconds === null) return '--'
  if (seconds < 60) return `${seconds < 10 ? seconds.toFixed(1) : Math.round(seconds)} 秒`
  if (seconds < 3600) return `${(seconds / 60).toFixed(seconds < 600 ? 1 : 0)} 分钟`
  return `${(seconds / 3600).toFixed(1)} 小时`
}

type PauseScope = 'GLOBAL' | 'PAID_SUBMISSIONS'

export function OperationsPanel({ adminId }: { adminId: string | null }) {
  const [snapshot, setSnapshot] = useState<OperationsSnapshot | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [pendingScope, setPendingScope] = useState<PauseScope | null>(null)
  const [confirmScope, setConfirmScope] = useState<PauseScope | null>(null)
  const refresh = useCallback(async () => {
    if (!adminId) return
    try { setSnapshot(await getOperations(adminId)); setError('') }
    catch (cause) { setError(cause instanceof ApiError ? `${cause.code}: ${cause.message}` : '暂时无法获取运行数据') }
  }, [adminId])
  useEffect(() => {
    let active = true
    let timer: number | undefined
    const poll = async () => {
      if (!document.hidden) await refresh()
      if (active) timer = window.setTimeout(() => void poll(), 15000)
    }
    timer = window.setTimeout(() => void poll(), 0)
    return () => {
      active = false
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [refresh])
  const toggle = async (scope: PauseScope, paused: boolean) => {
    if (!adminId || !snapshot) return
    setPendingScope(scope)
    setNotice('')
    try {
      await setOperationalPause(adminId, snapshot.runtime.version, scope, paused, `${scope.toLowerCase()} changed from operations console`)
      await refresh()
      setNotice(scope === 'GLOBAL'
        ? paused ? '任务调度已暂停，运行中的任务不会被取消。' : '任务调度已恢复，可以领取新的生成任务。'
        : paused ? '新的付费确认已暂停，已提交任务不受影响。' : '付费确认已恢复。')
    } catch (cause) { setError(cause instanceof Error ? cause.message : '暂停状态更新失败') }
    finally { setPendingScope(null); setConfirmScope(null) }
  }
  if (!adminId) return <section className="ops-empty"><AlertTriangle size={22} /><strong>无法获取管理员身份</strong></section>
  if (!snapshot) return <section className="ops-empty">{error ? <AlertTriangle size={22} /> : <LoaderCircle className="spin" size={22} />}<strong>{error || '正在加载运行状态'}</strong></section>
  const config = snapshot.runtime.config
  const pipeline = snapshot.pipelinePerformance
  const busy = pendingScope !== null
  const paidConfirmationBlockedByGlobal = !config.paidSubmissionsPaused && config.globalPaused
  return <section className="operations-console">
    <div className="ops-command-bar">
      <div><span>生产控制</span><h2>生产开关</h2><p>状态徽标表示当前情况，按钮文字表示点击后执行的操作。</p></div>
      <button className="secondary-button" disabled={busy} onClick={() => void refresh()}><RefreshCw size={16} />刷新状态</button>
    </div>
    <div className="ops-control-grid" aria-label="生产控制开关">
      <section className={`ops-control-card ${config.globalPaused ? 'is-paused' : 'is-running'}`}>
        <div className="ops-control-icon"><Workflow size={20} /></div>
        <div className="ops-control-copy">
          <div className="ops-control-title">
            <h3>任务调度</h3>
            <span className={`ops-control-state ${config.globalPaused ? 'is-paused' : 'is-running'}`} role="status" aria-live="polite"><i aria-hidden="true" />{config.globalPaused ? '已暂停' : '运行中'}</span>
          </div>
          <p id="global-scheduling-help">{config.globalPaused ? '不会启动新任务；正在运行的任务继续执行。' : '运行器可以领取并启动新的生成任务。'}</p>
        </div>
        <button
          className={`${config.globalPaused ? 'primary-button' : 'secondary-button secondary-button--danger'} ops-control-action`}
          disabled={busy}
          aria-describedby="global-scheduling-help"
          onClick={() => setConfirmScope('GLOBAL')}
        >
          {pendingScope === 'GLOBAL' ? <LoaderCircle className="spin" size={16} /> : config.globalPaused ? <Play size={16} /> : <Pause size={16} />}
          {pendingScope === 'GLOBAL' ? (config.globalPaused ? '正在恢复…' : '正在暂停…') : config.globalPaused ? '恢复任务调度' : '暂停任务调度'}
        </button>
      </section>
      <section className={`ops-control-card ${config.paidSubmissionsPaused ? 'is-paused' : paidConfirmationBlockedByGlobal ? 'is-blocked' : 'is-running'}`}>
        <div className="ops-control-icon"><CircleDollarSign size={20} /></div>
        <div className="ops-control-copy">
          <div className="ops-control-title">
            <h3>付费确认</h3>
            <span className={`ops-control-state ${config.paidSubmissionsPaused ? 'is-paused' : paidConfirmationBlockedByGlobal ? 'is-blocked' : 'is-running'}`} role="status" aria-live="polite"><i aria-hidden="true" />{config.paidSubmissionsPaused ? '已暂停' : paidConfirmationBlockedByGlobal ? '已开启 · 暂不可用' : '已开启'}</span>
          </div>
          <p id="paid-confirmation-help">{config.paidSubmissionsPaused ? '拒绝新的付费确认；已提交任务不会取消。' : paidConfirmationBlockedByGlobal ? '开关已开启，但受任务调度暂停影响，当前不可确认。' : '允许新任务确认、积分预留并进入生成流程。'}</p>
        </div>
        <button
          className={`${config.paidSubmissionsPaused ? 'primary-button' : 'secondary-button secondary-button--danger'} ops-control-action`}
          disabled={busy}
          aria-describedby="paid-confirmation-help"
          onClick={() => setConfirmScope('PAID_SUBMISSIONS')}
        >
          {pendingScope === 'PAID_SUBMISSIONS' ? <LoaderCircle className="spin" size={16} /> : config.paidSubmissionsPaused ? <Play size={16} /> : <Pause size={16} />}
          {pendingScope === 'PAID_SUBMISSIONS' ? (config.paidSubmissionsPaused ? '正在恢复…' : '正在暂停…') : config.paidSubmissionsPaused ? '恢复付费确认' : '暂停付费确认'}
        </button>
      </section>
    </div>
    {confirmScope ? <div className="ops-confirmation" role="alertdialog" aria-labelledby="ops-confirmation-title" aria-describedby="ops-confirmation-description">
      <span className="ops-confirmation-icon"><AlertTriangle size={19} /></span>
      <div><strong id="ops-confirmation-title">确认{confirmScope === 'GLOBAL' ? config.globalPaused ? '恢复任务调度' : '暂停任务调度' : config.paidSubmissionsPaused ? '恢复付费确认' : '暂停付费确认'}？</strong><p id="ops-confirmation-description">{confirmScope === 'GLOBAL'
        ? config.globalPaused ? '恢复后，运行器可以继续领取并启动新的生成任务。' : '暂停后不会启动新任务；已经运行的任务会继续执行。'
        : config.paidSubmissionsPaused ? '恢复后，新任务可以预留积分并进入生成队列。' : '暂停后拒绝新的付费确认；已提交任务不会取消。'}</p></div>
      <div><button className="secondary-button" disabled={busy} onClick={() => setConfirmScope(null)}>取消</button><button className={confirmScope === 'GLOBAL' ? config.globalPaused ? 'primary-button' : 'primary-button primary-button--danger' : config.paidSubmissionsPaused ? 'primary-button' : 'primary-button primary-button--danger'} disabled={busy} onClick={() => void toggle(confirmScope, confirmScope === 'GLOBAL' ? !config.globalPaused : !config.paidSubmissionsPaused)}>{busy ? <LoaderCircle className="spin" size={16} /> : null}确认执行</button></div>
    </div> : null}
    {error && <div className="service-alert" role="alert"><AlertTriangle size={18} /><span>{error}</span></div>}
    {notice && <div className="service-alert service-alert--success" role="status"><Play size={18} /><span>{notice}</span></div>}
    <div className="ops-metrics">
      <div><Gauge size={18} /><span><small>生成槽位利用率</small><strong>{Math.round(snapshot.metrics.generationSlotUtilization * 100)}%</strong></span></div>
      <div><Layers3 size={18} /><span><small>待生成 / 生成中</small><strong>{snapshot.queues.prepared} / {snapshot.queues.running}</strong></span></div>
      <div><Server size={18} /><span><small>活跃命令主机</small><strong>{snapshot.metrics.runnerActiveCommandHosts}</strong></span></div>
      <div><WalletCards size={18} /><span><small>已预留 / 状态不明积分</small><strong>{snapshot.metrics.pointsReserved} / {snapshot.metrics.pointsUncertain}</strong></span></div>
    </div>
    <section className="ops-band ops-pipeline" aria-labelledby="ops-pipeline-title">
      <div className="detail-heading"><div><span className="section-kicker">效率监控</span><h3 id="ops-pipeline-title">近 {pipeline.windowDays} 天流水线</h3></div><span>每 15 秒更新</span></div>
      <div className="ops-pipeline-summary">
        <span><Activity size={17} /><small>24 小时成片 / 任务</small><strong>{pipeline.throughput.completedVideos24h} / {pipeline.throughput.completedTasks24h}</strong></span>
        <span><Timer size={17} /><small>系统最慢阶段</small><strong>{pipeline.automationBottleneck ? stageLabels[pipeline.automationBottleneck] ?? pipeline.automationBottleneck : '等待样本'}</strong></span>
        <span><Gauge size={17} /><small>当前约束</small><strong>{constraintLabels[pipeline.currentConstraint] ?? pipeline.currentConstraint}</strong></span>
      </div>
      <div className="ops-stage-grid">
        {Object.entries(stageLabels).map(([key, label]) => {
          const stage = pipeline.stages[key]
          return <div key={key}><span><strong>{label}</strong><small>{stage?.sampleCount ?? 0} 个样本</small></span><span><small>p50 / p95</small><b>{formatDuration(stage?.p50Seconds ?? null)} / {formatDuration(stage?.p95Seconds ?? null)}</b></span></div>
        })}
      </div>
    </section>
    <div className="ops-band"><div className="detail-heading"><div><span className="section-kicker">生成容量</span><h3>并发与队列限制</h3></div><span>配置版本 v{snapshot.runtime.version}</span></div><div className="ops-capacity"><span>同一画布 <strong>{config.generationConcurrency.sameProject}</strong></span><span>单个用户 <strong>{config.generationConcurrency.perUser}</strong></span><span>全局并发 <strong>{config.generationConcurrency.global}</strong></span><span>队列水位 <strong>{config.preparedQueue.lowWatermark} / {config.preparedQueue.highWatermark}</strong></span></div></div>
    <div className="ops-columns">
      <section className="ops-band"><div className="detail-heading"><div><span className="section-kicker">运行器</span><h3>运行器主机</h3></div><span>{snapshot.runners.length}</span></div>{snapshot.runners.length ? snapshot.runners.map((runner) => <div className="ops-row" key={runner.id}><span><strong>{runner.hostname}</strong><small>{runnerStatusLabels[runner.status] ?? runner.status}</small></span><span>磁盘剩余 {runner.freeDiskPercent.toFixed(1)}%</span></div>) : <p className="ops-muted">尚未收到运行器心跳</p>}</section>
      <section className="ops-band"><div className="detail-heading"><div><span className="section-kicker">告警</span><h3>安全告警</h3></div><span>{snapshot.alerts.length}</span></div>{snapshot.alerts.length ? snapshot.alerts.map((alert) => <div className="ops-row ops-row--alert" key={alert.code}><AlertTriangle size={16} /><span><strong>{alertCodeLabels[alert.code] ?? alert.code}</strong><small>{alertActionLabels[alert.action] ?? alert.action}</small></span></div>) : <p className="ops-muted">当前没有安全告警</p>}</section>
    </div>
  </section>
}
