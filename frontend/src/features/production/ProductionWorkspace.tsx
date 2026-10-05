// 本文件由 App.tsx 拆分生成（2026-09-28 前端架构拆分 v2）。
// 代码为逐字搬运，未经逻辑改写。
import { AlertTriangle, ArrowLeft, Check, ChevronRight, LoaderCircle, MoreHorizontal, RefreshCw, RotateCcw, X } from 'lucide-react'
import { useState } from 'react'
import { analyzeTask, cancelTask, confirmTask, runPromptAssistant, saveTaskPrompts } from '../../api'
import { type Task, type Variant, type VariantKind } from '../../types'
import { currentProductionStageIndex, visibleProductionStageKeys } from '../../taskTiming'
import { providerPresentation } from '../../providerPresentation'
import { ACTIVE_PHASES, RESULT_PHASES } from '../../domain/workflowStates'
import { isAnalysisFailure, taskFailureMessage, taskStatus, variantDisplayName, variantErrorDetails, variantErrorMessage, variantErrorRetryable, variantKindDisplayName, variantKindShortLabel } from '../../domain/taskPresentation'
import { AuthenticatedImage } from '../../shared/components/Media'
import { TaskTimingTimeline } from '../../shared/components/TaskTiming'
import { ProviderBadge, TaskStatusBadge } from '../../shared/components/Badges'
import { type AnalysisResult, taskPrompt } from './productionTypes'
import { type PromptRevisionMode, AnalysisProgress, HistoricalPrompt, PlanPanel, VariantStatus } from './WorkspacePanels'

export function ProductionWorkspace({ task, onClose, onChanged, onRemix, onReuse, onPlay }: { task: Task; onClose: () => void; onChanged: () => Promise<void>; onRemix: () => void; onReuse: (variants: VariantKind[]) => void; onPlay: (variant: Variant) => void }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const reusableVariants = task.variants.filter((variant) => variant.promptText.trim())
  const [reuseKinds, setReuseKinds] = useState<VariantKind[]>(() => reusableVariants.map((variant) => variant.kind))
  const [confirmationKinds, setConfirmationKinds] = useState<VariantKind[]>(() => task.variants.map((variant) => variant.kind))
  const [promptDrafts, setPromptDrafts] = useState(() => ({
    stable: taskPrompt(task, 'STABLE'),
    dynamic: taskPrompt(task, 'DYNAMIC'),
  }))
  const [promptDirty, setPromptDirty] = useState<Record<VariantKind, boolean>>({ STABLE: false, DYNAMIC: false })
  const [revisionInstructions, setRevisionInstructions] = useState<Record<VariantKind, string>>({ STABLE: '', DYNAMIC: '' })
  const [revisionMessages, setRevisionMessages] = useState<Record<VariantKind, string>>({ STABLE: '', DYNAMIC: '' })
  const [activeRevision, setActiveRevision] = useState<{ kind: VariantKind; mode: PromptRevisionMode } | null>(null)
  const promptsDirty = promptDirty.STABLE || promptDirty.DYNAMIC
  const analysis = task.analysisResult as AnalysisResult | null
  const provider = providerPresentation(task.generationProvider)
  const isFixedWorkflow = task.workflowKind === 'FIXED_TEMPLATE'
  const isCustomWorkflow = isFixedWorkflow && task.settings?.generationMode === 'custom'
  const stable = task.variants.find((variant) => variant.kind === 'STABLE')
  const dynamic = task.variants.find((variant) => variant.kind === 'DYNAMIC')
  const savePrompts = async (sourceTask = task) => {
    if (!promptDrafts.stable.trim() || !promptDrafts.dynamic.trim()) throw new Error('稳定展示和动态广告的提示词不能为空')
    const changed = await saveTaskPrompts(sourceTask, promptDrafts.stable, promptDrafts.dynamic)
    setPromptDrafts({
      stable: taskPrompt(changed, 'STABLE'),
      dynamic: taskPrompt(changed, 'DYNAMIC'),
    })
    return changed
  }
  const revisePrompt = async (kind: VariantKind, mode: PromptRevisionMode) => {
    const typedInstruction = revisionInstructions[kind].trim()
    if (mode === 'MODIFY' && !typedInstruction) {
      setError('请先用一句话描述想怎么修改')
      return
    }
    const instruction = mode === 'MODIFY'
      ? typedInstruction
      : `重新生成${kind === 'STABLE' ? '稳定展示' : '动态广告'}方案，在不改变服装事实和方案定位的前提下优化动作和镜头。`
    setBusy(true)
    setActiveRevision({ kind, mode })
    setError('')
    setRevisionMessages((current) => ({ ...current, [kind]: '' }))
    try {
      const result = await runPromptAssistant(task, 'REGENERATE', instruction, promptDrafts.stable, promptDrafts.dynamic, kind)
      setPromptDrafts({
        stable: taskPrompt(result.task, 'STABLE'),
        dynamic: taskPrompt(result.task, 'DYNAMIC'),
      })
      setPromptDirty({ STABLE: false, DYNAMIC: false })
      setRevisionMessages((current) => ({ ...current, [kind]: mode === 'MODIFY' ? '已按这句话修改此方案' : '已重新生成此方案' }))
      if (mode === 'MODIFY') setRevisionInstructions((current) => ({ ...current, [kind]: '' }))
      await onChanged()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '大模型处理失败，请稍后重试')
    } finally {
      setBusy(false)
      setActiveRevision(null)
    }
  }
  const confirm = async () => {
    setBusy(true)
    setError('')
    try {
      const currentTask = promptsDirty ? await savePrompts() : task
      await confirmTask(currentTask, confirmationKinds)
      await onChanged()
    } catch (cause) { setError(cause instanceof Error ? cause.message : '确认失败，请稍后重试') } finally { setBusy(false) }
  }
  const retryAnalysis = async () => {
    setBusy(true)
    setError('')
    try {
      await analyzeTask(task)
      await onChanged()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '重新分析启动失败，请稍后重试')
    } finally { setBusy(false) }
  }
  const cancel = async () => {
    if (!window.confirm(`确定取消此任务吗？已提交到 ${providerPresentation(task.generationProvider).displayName} 的远端任务可能无法撤回。`)) return
    setBusy(true)
    setError('')
    try {
      await cancelTask(task.id)
      await onChanged()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '任务取消失败，请稍后重试')
    } finally { setBusy(false) }
  }
  const isConfirmation = !isFixedWorkflow && task.phase === 'AWAITING_CONFIRMATION'
  const isGenerating = ACTIVE_PHASES.has(task.phase) && task.phase !== 'DRAFT' && task.phase !== 'ANALYZING'
  const isCompleted = RESULT_PHASES.has(task.phase)
  const canReuse = !isFixedWorkflow && isCompleted && task.actionCapabilities.canRegenerate && reusableVariants.length > 0
  const analysisFailure = isAnalysisFailure(task)
  const productionStageKeys = visibleProductionStageKeys(
    task.workflowKind,
    task.settings?.generationMode,
  )
  const currentStep = currentProductionStageIndex(
    task.phase,
    task.workflowKind,
    task.settings?.generationMode,
  )
  const needsRecovery = task.phase === 'ACTION_REQUIRED'
  const confirmationChoice = confirmationKinds.length === 2
    ? 'BOTH'
    : confirmationKinds[0] ?? task.variants[0]?.kind
  const confirmationLabel = confirmationKinds.length === 2
    ? '全部方案'
    : variantKindDisplayName(confirmationKinds[0] ?? task.variants[0]?.kind ?? 'STABLE')
  return <div className="workspace-view">
    <section className="production-workspace" aria-labelledby="detail-title">
      <header className="drawer-header">
        <button className="icon-button" onClick={onClose} aria-label="关闭任务详情"><ArrowLeft size={19} /></button>
        <div className="drawer-header-main"><span>任务 / {isConfirmation ? '方案确认' : RESULT_PHASES.has(task.phase) ? '视频结果' : analysisFailure ? '分析恢复' : needsRecovery ? '异常处理' : '生产进度'}</span><h1 id="detail-title">{task.title}</h1></div>
        <div className="drawer-header-actions"><ProviderBadge provider={task.generationProvider} /><TaskStatusBadge task={task} /></div>
      </header>
      <div className="workspace-stages" aria-label="制作阶段">{productionStageKeys.map((stageKey, index) => {
        const label = stageKey === 'MATERIALS' ? '素材'
          : stageKey === 'TEMPLATE' ? '模板'
            : stageKey === 'PREFLIGHT' ? '预检'
              : stageKey === 'ANALYSIS' ? '分析'
                : stageKey === 'PLAN' ? '方案'
                  : stageKey === 'RESULT' ? '结果'
                    : provider.kind === 'legacy' ? '历史任务生成' : `${provider.displayName}生成`
        return <div key={stageKey} aria-current={index === currentStep ? 'step' : undefined} className={index < currentStep ? 'is-complete' : index === currentStep ? 'is-current' : ''}><span>{index < currentStep ? <Check size={14} /> : index + 1}</span><strong>{label}</strong></div>
      })}</div>
      <div className="drawer-content">
        <section className="source-summary"><div className="source-assets">{[...task.assets].sort((a, b) => a.order - b.order).map((asset, index) => <figure key={asset.id}><AuthenticatedImage src={asset.thumbnailUrl} alt={asset.originalFilename} /><figcaption>{asset.role === 'PRODUCT' || asset.usedForGeneration === false ? '产品图' : `分镜 ${index + 1}`}</figcaption></figure>)}</div><div className="garment-summary"><span>{isCustomWorkflow ? '自定义直达快照' : isFixedWorkflow ? '自动化生成快照' : '服装识别摘要'}</span><strong>{isCustomWorkflow ? '自定义提示词 · 默认生产规格' : isFixedWorkflow ? `${task.siteProfileId ?? '未知站点'} · 自动编排` : [analysis?.garmentFacts?.category, analysis?.garmentFacts?.mainColor, analysis?.garmentFacts?.fit].filter(Boolean).join(' · ') || '正在整理服装信息'}</strong><p>{isCustomWorkflow ? `提示词原文直达 · ${task.variants.length} 个结果` : isFixedWorkflow ? `动作 ${String(task.settings?.actionIntensity ?? 'standard')} · ${task.variants.length} 个结果` : analysis?.consistencyObservations?.summary ?? '系统将优先保持服装结构、颜色、印花和文字准确。'}</p></div></section>
        {analysisFailure ? <section className="analysis-recovery" role="alert">
          <span className="analysis-recovery-icon"><AlertTriangle size={22} /></span>
          <div><span>方案尚未生成</span><h2>{taskStatus(task).label}</h2><p>{taskFailureMessage(task)} 重新分析会继续使用当前素材，并按素材数量重新计算等待时间。</p></div>
          <button className="primary-button" disabled={busy || !task.actionCapabilities.canRetryAnalysis} onClick={() => void retryAnalysis()}>{busy ? <LoaderCircle className="spin" size={17} /> : <RefreshCw size={17} />}重新分析方案</button>
        </section> : null}
        {needsRecovery && !analysisFailure ? <section className="analysis-recovery" role="alert">
          <span className="analysis-recovery-icon"><AlertTriangle size={22} /></span>
          <div><span>提交前预检已停止</span><h2>{provider.displayLabel} 未收到生成任务</h2><p>{taskFailureMessage(task)}</p></div>
        </section> : null}
        {isConfirmation ? <>
          <div className="drawer-section-title"><div><span>步骤 2 / 3</span><h2>确认视频方案</h2></div><p>确认后将保存提示词原文快照，并原样提交给 {provider.displayLabel}。</p></div>
          <div className={`plans-grid${task.variants.length === 1 ? ' plans-grid--single' : ''}`}>
            {stable ? <PlanPanel kind="STABLE" plan={analysis?.stablePlan} variant={stable} risks={analysis?.riskFlags ?? []} prompt={promptDrafts.stable} promptDirty={promptDirty.STABLE} disabled={busy} revisionInstruction={revisionInstructions.STABLE} revisionMessage={revisionMessages.STABLE} activeRevisionMode={activeRevision?.kind === 'STABLE' ? activeRevision.mode : null} onPromptChange={(value) => { setPromptDrafts((current) => ({ ...current, stable: value })); setPromptDirty((current) => ({ ...current, STABLE: true })) }} onRevisionInstructionChange={(value) => setRevisionInstructions((current) => ({ ...current, STABLE: value }))} onPromptRevision={(mode) => void revisePrompt('STABLE', mode)} /> : null}
            {dynamic ? <PlanPanel kind="DYNAMIC" plan={analysis?.dynamicPlan} variant={dynamic} risks={analysis?.riskFlags ?? []} prompt={promptDrafts.dynamic} promptDirty={promptDirty.DYNAMIC} disabled={busy} revisionInstruction={revisionInstructions.DYNAMIC} revisionMessage={revisionMessages.DYNAMIC} activeRevisionMode={activeRevision?.kind === 'DYNAMIC' ? activeRevision.mode : null} onPromptChange={(value) => { setPromptDrafts((current) => ({ ...current, dynamic: value })); setPromptDirty((current) => ({ ...current, DYNAMIC: true })) }} onRevisionInstructionChange={(value) => setRevisionInstructions((current) => ({ ...current, DYNAMIC: value }))} onPromptRevision={(mode) => void revisePrompt('DYNAMIC', mode)} /> : null}
          </div>
        </> : null}
        {isGenerating || RESULT_PHASES.has(task.phase) || (task.phase === 'ACTION_REQUIRED' && !analysisFailure) ? <>
          <div className="drawer-section-title"><div><span>步骤 3 / 3 · {provider.displayLabel}</span><h2>{RESULT_PHASES.has(task.phase) ? '视频结果' : needsRecovery ? `${provider.displayLabel} 任务需要处理` : `${provider.displayLabel} 生成进度`}</h2></div></div>
          <TaskTimingTimeline task={task} />
          <div className="variant-status-list">{task.variants.map((variant) => <VariantStatus key={variant.id} task={task} variant={variant} onChanged={onChanged} onPlay={() => onPlay(variant)} />)}</div>
        </> : null}
        {isCompleted && reusableVariants.length ? <>
          <div className="drawer-section-title history-prompt-title"><div><span>历史方案</span><h2>本次使用的提示词</h2></div><p>提示词为任务完成时的只读快照</p></div>
          <div className={`history-prompts${reusableVariants.length === 1 ? ' history-prompts--single' : ''}`}>
            {reusableVariants.map((variant) => <HistoricalPrompt key={variant.id} task={task} variant={variant} selected={reuseKinds.includes(variant.kind)} />)}
          </div>
        </> : null}
        {task.phase === 'ANALYZING' ? <AnalysisProgress task={task} /> : null}
        {error ? <div className="inline-alert inline-alert--danger" role="alert"><AlertTriangle size={17} />{error}</div> : null}
        <details className="technical-details"><summary><span><MoreHorizontal size={17} />技术信息</span><ChevronRight size={16} /></summary><div><dl><dt>Task ID</dt><dd>{task.id}</dd><dt>Session ID</dt><dd>{task.clientTaskId}</dd><dt>工作流</dt><dd>{isFixedWorkflow ? '固定模板' : '历史分析流程'}</dd><dt>生成通道</dt><dd>{provider.displayLabel}</dd>{provider.kind === 'legacy' ? <><dt>历史项目 ID</dt><dd>{task.canvasProjectUuid ?? '尚未分配'}</dd></> : <><dt>调用方式</dt><dd>{provider.displayLabel} / 远端任务查询</dd></>}<dt>原始状态</dt><dd>{task.phase}</dd><dt>状态版本</dt><dd>{task.stateVersion}</dd><dt>错误代码</dt><dd>{task.phaseReasonCode ?? '无'}</dd></dl><div className="prompt-hashes">{task.variants.map((variant) => <span key={variant.id}><strong>{variantDisplayName(variant)} · {providerPresentation(variant.provider || task.generationProvider).displayLabel}</strong><code>{variant.providerTaskId ? `${providerPresentation(variant.provider || task.generationProvider).kind === 'kling' ? 'remoteTaskId' : 'taskId'}: ${variant.providerTaskId}` : `Prompt Hash: ${variant.promptHash ?? '尚未锁定'}`}</code><small>{variant.executionBackend ?? '尚未进入生成通道'}</small>{variant.errorCode ? <small>错误：{variant.errorCode}{variantErrorMessage(variant) ? ` · ${variantErrorMessage(variant)}` : ''}{variantErrorRetryable(variant) === true ? ' · 可以重试' : variantErrorRetryable(variant) === false ? ' · 需要人工处理' : ''}</small> : null}{variantErrorDetails(variant) ? <code>{JSON.stringify(variantErrorDetails(variant))}</code> : null}</span>)}</div></div></details>
      </div>
      {task.actionCapabilities.canRegenerate || task.actionCapabilities.canCancel || isConfirmation ? <footer className={`drawer-footer${canReuse ? ' drawer-footer--reuse' : ''}${isConfirmation ? ' drawer-footer--confirmation' : ''}`}>
        <div className="drawer-footer-actions">
          {task.actionCapabilities.canCancel ? <button className="secondary-button secondary-button--danger" disabled={busy} onClick={() => void cancel()}><X size={16} />取消任务</button> : null}
          {task.actionCapabilities.canRegenerate && !canReuse ? <button className="secondary-button" onClick={onRemix}><RotateCcw size={16} />使用相同素材再制作</button> : null}
        </div>
        {canReuse ? <div className="reuse-controls">
          <fieldset>
            <legend>选择复用方案</legend>
            {(['STABLE', 'DYNAMIC'] as VariantKind[]).map((kind) => {
              const available = reusableVariants.some((variant) => variant.kind === kind)
              const checked = reuseKinds.includes(kind)
              return <label key={kind} className={`${checked ? 'is-selected' : ''}${available ? '' : ' is-disabled'}`}>
                <input
                  type="checkbox"
                  checked={checked}
                  disabled={!available}
                  onChange={() => setReuseKinds((current) => checked ? current.filter((item) => item !== kind) : [...current, kind].sort((a) => a === 'STABLE' ? -1 : 1))}
                />
                <span className={`variant-label ${kind === 'STABLE' ? 'variant-label--a' : 'variant-label--b'}`}>{variantKindShortLabel(kind)}</span>
                <span><strong>{variantKindDisplayName(kind)}</strong>{!available ? <small>无历史提示词</small> : null}</span>
              </label>
            })}
          </fieldset>
          <div>
            {!reuseKinds.length ? <small role="alert">请至少勾选一个方案</small> : <small>将复用全部素材及所选提示词，并跳过图片分析</small>}
            <button className="primary-button primary-button--large" disabled={!reuseKinds.length} onClick={() => onReuse(reuseKinds)}><RotateCcw size={17} />一键复用并生成 {reuseKinds.length || ''} 个结果</button>
          </div>
        </div> : null}
        {isConfirmation ? <div className="confirmation-submit">
          {task.variants.length > 1 ? <fieldset className="confirmation-variant-picker">
            <legend>本次生成</legend>
            <div>
              <label className={confirmationChoice === 'STABLE' ? 'is-selected' : ''}>
                <input type="radio" name={`confirmation-variant-${task.id}`} checked={confirmationChoice === 'STABLE'} disabled={busy} onChange={() => setConfirmationKinds(['STABLE'])} />
                <span>稳定展示</span>
              </label>
              <label className={confirmationChoice === 'BOTH' ? 'is-selected' : ''}>
                <input type="radio" name={`confirmation-variant-${task.id}`} checked={confirmationChoice === 'BOTH'} disabled={busy} onChange={() => setConfirmationKinds(['STABLE', 'DYNAMIC'])} />
                <span>全部方案</span>
              </label>
              <label className={confirmationChoice === 'DYNAMIC' ? 'is-selected' : ''}>
                <input type="radio" name={`confirmation-variant-${task.id}`} checked={confirmationChoice === 'DYNAMIC'} disabled={busy} onChange={() => setConfirmationKinds(['DYNAMIC'])} />
                <span>动态广告</span>
              </label>
            </div>
          </fieldset> : null}
          <button className="primary-button primary-button--large" disabled={busy} onClick={() => void confirm()}>{busy ? <LoaderCircle className="spin" size={18} /> : <Check size={18} />}确认并生成 {confirmationLabel}</button>
        </div> : null}
      </footer> : null}
    </section>
  </div>
}
