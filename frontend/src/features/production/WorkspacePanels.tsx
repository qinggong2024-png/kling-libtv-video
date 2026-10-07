// 本文件由 App.tsx 拆分生成（2026-09-28 前端架构拆分 v2）。
// 代码为逐字搬运，未经逻辑改写。
import { AlertTriangle, Check, CheckCircle2, Copy, Download, LoaderCircle, LockKeyhole, Play, RefreshCw, ShieldCheck, WandSparkles } from 'lucide-react'
import { useEffect, useState } from 'react'
import { restoreOutput, saveArtifact } from '../../api'
import { type Task, type Variant, type VariantKind } from '../../types'
import { formatRiskFlags } from '../../riskLabels'
import { formatElapsed, parseTaskTimestamp } from '../../taskTiming'
import { variantExecutionMessage } from '../../providerPresentation'
import { variantDisplayName, variantFileToken, variantKindDisplayName, variantKindShortLabel, variantLabelClass, variantShortLabel } from '../../domain/taskPresentation'
import { copyText } from '../../shared/utils/copyText'
import { ProviderBadge, StatusBadge } from '../../shared/components/Badges'
import { analysisStageLabels } from '../../domain/workflowStates'
import { type VariantPlan } from './productionTypes'

export function PromptBlock({ variant, value, disabled, dirty, onChange }: { variant: Variant; value: string; disabled: boolean; dirty: boolean; onChange: (value: string) => void }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    await copyText(value)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1600)
  }
  const inputId = `prompt-${variant.id}`
  return <div className="prompt-block"><div><label htmlFor={inputId}>最终提示词方案</label><span className={dirty ? 'unsaved-badge' : 'snapshot-tag'}>{dirty ? '确认时保存' : <><LockKeyhole size={13} />确认后锁定</>}</span></div><textarea id={inputId} value={value} disabled={disabled} maxLength={2000} onChange={(event) => onChange(event.target.value)} /><div className="prompt-block-actions"><span>{value.length} / 2000</span><button className="compact-button" disabled={!value} onClick={() => void copy()}>{copied ? <Check size={15} /> : <Copy size={15} />}{copied ? '已复制' : '复制'}</button></div></div>
}

export type PromptRevisionMode = 'REGENERATE' | 'MODIFY'

export function PromptRevision({
  kind,
  instruction,
  message,
  disabled,
  activeMode,
  onInstructionChange,
  onSubmit,
}: {
  kind: VariantKind
  instruction: string
  message: string
  disabled: boolean
  activeMode: PromptRevisionMode | null
  onInstructionChange: (value: string) => void
  onSubmit: (mode: PromptRevisionMode) => void
}) {
  const inputId = `prompt-revision-${kind.toLowerCase()}`
  return <section className="prompt-revision" aria-labelledby={`${inputId}-title`}>
    <div className="prompt-revision-heading">
      <div><WandSparkles size={16} /><span><strong id={`${inputId}-title`}>调整此方案</strong><small>重新生成，或用一句话精准修改</small></span></div>
      <button className="secondary-button" disabled={disabled} onClick={() => onSubmit('REGENERATE')}>{activeMode === 'REGENERATE' ? <LoaderCircle className="spin" size={16} /> : <RefreshCw size={16} />}重新生成</button>
    </div>
    <div className="prompt-revision-input">
      <label className="sr-only" htmlFor={inputId}>一句话修改当前方案</label>
      <input id={inputId} value={instruction} maxLength={2000} disabled={disabled} placeholder="例如：减少转身，增加服装正面特写" onChange={(event) => onInstructionChange(event.target.value)} onKeyDown={(event) => {
        if (event.key === 'Enter' && instruction.trim() && !disabled) onSubmit('MODIFY')
      }} />
      <button className="primary-button" disabled={disabled || !instruction.trim()} onClick={() => onSubmit('MODIFY')}>{activeMode === 'MODIFY' ? <LoaderCircle className="spin" size={16} /> : <WandSparkles size={16} />}一句话修改</button>
    </div>
    {message ? <p className="prompt-revision-message" role="status"><CheckCircle2 size={15} />{message}</p> : null}
  </section>
}

export function PlanPanel({
  kind,
  plan,
  variant,
  risks,
  prompt,
  promptDirty,
  disabled,
  revisionInstruction,
  revisionMessage,
  activeRevisionMode,
  onPromptChange,
  onRevisionInstructionChange,
  onPromptRevision,
}: {
  kind: VariantKind
  plan?: VariantPlan
  variant?: Variant
  risks: string[]
  prompt: string
  promptDirty: boolean
  disabled: boolean
  revisionInstruction: string
  revisionMessage: string
  activeRevisionMode: PromptRevisionMode | null
  onPromptChange: (value: string) => void
  onRevisionInstructionChange: (value: string) => void
  onPromptRevision: (mode: PromptRevisionMode) => void
}) {
  const stable = kind === 'STABLE'
  const shots = plan?.shots ?? []
  const first = shots[0]
  return <section className={`plan-panel ${stable ? 'plan-panel--stable' : 'plan-panel--dynamic'}`}>
    <header><span className={`variant-label ${stable ? 'variant-label--a' : 'variant-label--b'}`}>{variantKindShortLabel(kind)}</span><div><h3>{variantKindDisplayName(kind)}</h3><p>{stable ? '保持人物稳定与服装结构准确，清晰展示印花和版型' : '强化广告开场和动作变化，同时保持服装准确'}</p></div></header>
    <div className="plan-facts"><div><span>{stable ? '视频开场' : '开场钩子'}</span><strong>{first?.shotFunction ?? (stable ? '清晰产品开场' : '强动态广告开场')}</strong></div><div><span>人物动作</span><strong>{first?.action ?? '自然动作'}</strong></div><div><span>镜头运动</span><strong>{first?.camera ?? '稳定运镜'}</strong></div><div><span>展示重点</span><strong>{first?.productDisplay ?? '服装轮廓与细节'}</strong></div></div>
    {shots.length > 1 ? <div className="shot-strip">{shots.map((shot, index) => <span key={`${shot.shotFunction}-${index}`}><strong>动作段 {index + 1}</strong><small>{[shot.entryState, shot.action, shot.exitState].filter(Boolean).join(' → ')}</small></span>)}</div> : null}
    <div className={`risk-line ${risks.length ? 'risk-line--warning' : ''}`}>{risks.length ? <AlertTriangle size={15} /> : <ShieldCheck size={15} />}<span>{risks.length ? `风险提示：${formatRiskFlags(risks)}` : '未发现明显的产品准确性风险'}</span></div>
    {variant ? <><PromptBlock variant={variant} value={prompt} dirty={promptDirty} disabled={disabled} onChange={onPromptChange} /><PromptRevision kind={kind} instruction={revisionInstruction} message={revisionMessage} disabled={disabled} activeMode={activeRevisionMode} onInstructionChange={onRevisionInstructionChange} onSubmit={onPromptRevision} /></> : null}
  </section>
}

export function VariantStatus({ task, variant, onChanged, onPlay }: { task: Task; variant: Variant; onChanged: () => Promise<void>; onPlay: () => void }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const ready = Boolean(variant.downloadArtifactId)
  const unknown = variant.generationStatus === 'UNKNOWN'
  const downloading = variant.downloadStatus === 'DOWNLOADING'
  const restore = async () => {
    setBusy(true)
    setError('')
    try {
      await restoreOutput(task.id, variant.kind)
      await onChanged()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '远端成品恢复失败，请稍后重试')
    } finally { setBusy(false) }
  }
  const download = async () => {
    if (!variant.downloadArtifactId) return
    setBusy(true)
    setError('')
    try {
      await saveArtifact(variant.downloadArtifactId, `${task.title}-${variantFileToken(variant)}.mp4`)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '视频下载失败，请稍后重试')
    } finally { setBusy(false) }
  }
  const canRestore = !ready
    && !downloading
    && ['SUCCEEDED', 'PARTIAL'].includes(variant.generationStatus)
    && (variant.downloadStatus === 'FAILED' || task.phase === 'ACTION_REQUIRED')
  return <div className="variant-status"><span className={`variant-label ${variantLabelClass(variant)}`}>{variantShortLabel(variant)}</span><div><strong>{variantDisplayName(variant)}</strong><ProviderBadge provider={variant.provider || task.generationProvider} /><StatusBadge value={variant.generationStatus} retryable={variant.retryable ?? variant.providerErrorRetryable} hasArtifact={ready} /><small>{variantExecutionMessage(variant, task.generationProvider, task.phase)}</small>{error ? <small className="variant-action-error" role="alert">{error}</small> : null}</div><div className="variant-status-actions">
    {ready ? <><button className="compact-button" onClick={onPlay}><Play size={15} />播放</button><button className="compact-button" disabled={busy} onClick={() => void download()}>{busy ? <LoaderCircle className="spin" size={15} /> : <Download size={15} />}下载</button></> : null}
    {downloading ? <button className="compact-button" disabled><LoaderCircle className="spin" size={15} />下载中</button> : null}
    {canRestore ? <button className="compact-button" disabled={busy} onClick={() => void restore()}>{busy ? <LoaderCircle className="spin" size={15} /> : <RefreshCw size={15} />}恢复远端成品</button> : null}
    {unknown ? <button className="compact-button" onClick={() => void onChanged()}><RefreshCw size={15} />重新查询状态</button> : null}
  </div></div>
}

export function HistoricalPrompt({
  task,
  variant,
  selected,
}: {
  task: Task
  variant: Variant
  selected: boolean
}) {
  const [copyStatus, setCopyStatus] = useState<'idle' | 'copied' | 'failed'>('idle')
  const copy = async () => {
    try {
      await copyText(variant.promptText)
      setCopyStatus('copied')
    } catch {
      setCopyStatus('failed')
    }
    window.setTimeout(() => setCopyStatus('idle'), 1600)
  }
  return <article className={`history-prompt${selected ? ' is-selected' : ''}`}>
    <header>
      <span className={`variant-label ${variantLabelClass(variant)}`}>{variantShortLabel(variant)}</span>
      <span><strong>{variantDisplayName(variant)}</strong><small>{task.workflowKind === 'FIXED_TEMPLATE' ? task.settings?.generationMode === 'custom' ? '自定义直达快照' : '自动化编译快照' : selected ? '将复用此提示词' : '本次不复用'}</small></span>
      <button className="compact-button" type="button" onClick={() => void copy()} aria-live="polite">{copyStatus === 'copied' ? <Check size={15} /> : <Copy size={15} />}{copyStatus === 'copied' ? '已复制' : copyStatus === 'failed' ? '复制失败' : '复制'}</button>
    </header>
    <p>{variant.promptText}</p>
  </article>
}

export function AnalysisProgress({ task }: { task: Task }) {
  const [now, setNow] = useState(Date.now)
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 10_000)
    return () => window.clearInterval(timer)
  }, [])
  const lastActiveAt = task.analysisHeartbeatAt ?? task.analysisStartedAt ?? task.updatedAt
  const elapsedSeconds = Math.max(0, Math.floor((now - parseTaskTimestamp(lastActiveAt)) / 1000))
  const manyImages = task.assetCount > 4
  const longRunning = task.analysisStartedAt !== null
    && now - parseTaskTimestamp(task.analysisStartedAt) >= 120_000
  const stageLabel = task.analysisStage ? analysisStageLabels[task.analysisStage] : undefined
  const activeText = elapsedSeconds < 45
    ? '刚刚'
    : `${formatElapsed(lastActiveAt, now)}前`
  return <div className="detail-analysis" role="status" aria-live="polite">
    <LoaderCircle className="spin" size={24} />
    <div>
      <strong>{stageLabel ?? (longRunning ? '后台仍在分析，已自动查询状态' : `正在分析 ${task.assetCount} 张素材`)}</strong>
      <span>{longRunning
        ? `后台任务仍在运行，最近一次活跃于${activeText}；页面会持续查询状态。`
        : manyImages
          ? '素材较多，系统已按数量延长等待时间；完成后进入方案确认。'
          : `正在识别服装结构、人物场景和适合的视频动作，最近一次活跃于${activeText}。`}</span>
    </div>
  </div>
}
