import { Check, FileImage, LockKeyhole, RefreshCw, WandSparkles, X } from 'lucide-react'
import { ImageUploadTrigger } from '../../shared/components/studio/ImageUploadTrigger'
import { useEffect, useMemo, useRef, useState, type ChangeEvent } from 'react'
import { getSiteStyleProfiles } from '../../api'
import { useOptionalCreativeProject } from '../../creative-project/hooks'
import type { CreativeIntelligenceSnapshot } from '../../creative-project/types'
import type { SiteStyleProfileSummary } from '../../types'
import { createUuid } from '../../uuid'
import {
  createDirectorProduct,
  createDirectorTask,
  getDirectorProduct,
  getDirectorTask,
  sendDirectorCommand,
  type DirectorCommandInput,
  type DirectorTaskResponse,
  type DirectorCandidate,
} from './directorApi'
import {
  createDirectorDraft,
  canReviewDirectorCandidate,
  canSelectDirectorCandidate,
  canReviewDirectorStoryboardCandidate,
  canSelectDirectorStoryboardCandidate,
  canAuthorizeStoryboard,
  directionsFromAnalysis,
  isDirectorIntakeReady,
  selectDirectorDirection,
  type DirectorDraft,
  type DirectorDirection,
  type DirectorProductIntake,
} from './directorModel'
import {
  selectDirectorFirstFrameCandidates,
  selectDirectorPlanningSnapshot,
  selectDirectorStoryboardCandidates,
  selectDirectorStoryboardPackage,
  selectDirectorStoryboardReview,
  selectDirectorStoryboardSelection,
  selectDirectorTaskRecovery,
} from './directorSelectors'
import {
  classifyDirectorRecoveryError,
  createDirectorTaskRecovery,
  directorRecoveryMessage,
  draftFromPersistedDirectorProject,
  validateDirectorProductReference,
  validateDirectorTaskRecovery,
} from './directorRecovery'
import { prepareProductionBridge } from './productionBridge'
import { selectDirectorEvidence } from './directorEvidence'
import { explainDirectorFailure } from './directorPresentation'
import { DirectorAnalysisTrace, DirectorBridgeStatus, DirectorDirectionCard, DirectorPackageEvidence } from './DirectorPlanningViews'
import { DirectorBrandDNAView } from './DirectorBrandDNAView'
import { selectDirectorBrandProfile } from './directorBrandDNA'
import { HumanReviewPanel } from '../human-review/HumanReviewPanel'
import { CreativePackageExportView } from './CreativePackageExportView'
import './directorStudio.css'

function updateProjectSnapshot(
  snapshot: CreativeIntelligenceSnapshot | undefined,
): CreativeIntelligenceSnapshot | undefined {
  return snapshot
}

type DirectorStageKey = 'brief' | 'direction' | 'package'

export function DirectorStudio() {
  const projectContext = useOptionalCreativeProject()
  const [draft, setDraft] = useState<DirectorDraft>(createDirectorDraft)
  const [workflow, setWorkflow] = useState<DirectorTaskResponse | null>(null)
  const [brandProfiles, setBrandProfiles] = useState<SiteStyleProfileSummary[]>([])
  const [brandProfilesLoading, setBrandProfilesLoading] = useState(true)
  const [brandProfilesError, setBrandProfilesError] = useState('')
  const [selectedBrandId, setSelectedBrandId] = useState('')
  const [busyAction, setBusyAction] = useState<'analyze' | 'select' | 'authorize' | 'generate' | 'authorize_storyboard' | 'generate_storyboard' | 'review' | 'select_frame' | 'select_storyboard' | 'refresh' | null>(null)
  const [rejectionReasons, setRejectionReasons] = useState<Record<string, string>>({})
  const [notice, setNotice] = useState('')
  const [viewedStage, setViewedStage] = useState<DirectorStageKey | null>(null)
  const clientKeyRef = useRef(createUuid())
  const frontImageInputRef = useRef<HTMLInputElement>(null)
  const productIdRef = useRef<string | undefined>(undefined)
  const recoveryAttemptRef = useRef<string | null>(null)
  const commandRef = useRef<{ fingerprint: string; key: string } | null>(null)
  const directionsRef = useRef<HTMLElement>(null)
  const directionsHeadingRef = useRef<HTMLHeadingElement>(null)
  const authorizationRef = useRef<{
    fingerprint: string
    payload: NonNullable<DirectorCommandInput['authorization']>
  } | null>(null)
  const chosenBrand = selectDirectorBrandProfile(brandProfiles, selectedBrandId, draft.intake.brandName)
  const ready = isDirectorIntakeReady(draft.intake) && (draft.intake.brandMode !== 'brand' || Boolean(chosenBrand))
  const hasAnalysis = Boolean(workflow?.snapshot.plan)
  const canRetryAnalysis = workflow?.status === 'DRAFT' || workflow?.status === 'ANALYSIS_FAILED'
  const selectedDirection = draft.directions.find((direction) => direction.id === draft.selectedDirectionId) ?? null
  const confirmedDirectionId = workflow?.snapshot.package
    ? workflow.snapshot.plan?.selected_direction ?? draft.selectedDirectionId
    : null
  const directionConfirmed = Boolean(confirmedDirectionId)
  const firstFrameCandidates = selectDirectorFirstFrameCandidates(workflow)
  const storyboardPackage = selectDirectorStoryboardPackage(workflow)
  const storyboardCandidates = selectDirectorStoryboardCandidates(workflow)
  const storyboardSelection = selectDirectorStoryboardSelection(workflow)
  const storyboardReview = selectDirectorStoryboardReview(workflow)
  const packageState = workflow?.snapshot.package
    ? workflow.status === 'STORYBOARD_REVIEW'
      ? 'Fake 分镜已生成，等待人工查看'
      : workflow.status === 'IMAGE_REVIEW' && firstFrameCandidates.length
        ? 'Fake 首帧已生成，等待人工查看'
        : storyboardPackage
          ? '首帧已选，分镜生产包已锁定'
          : '生产包已锁定'
    : selectedDirection
      ? `已选择 ${selectedDirection.id} · ${selectedDirection.title}，等待确认`
      : '确认方向后生成生产包预览'
  const snapshot = useMemo(
    () => updateProjectSnapshot(projectContext?.project.intelligenceSnapshot),
    [projectContext?.project.intelligenceSnapshot],
  )
  const bridgePreparation = prepareProductionBridge(
    workflow ? selectDirectorPlanningSnapshot(workflow, draft, projectContext?.project.id, snapshot).handoff : null,
  )
  const evidence = selectDirectorEvidence(workflow)
  const stage = busyAction === 'analyze' || workflow?.status === 'ANALYZING'
    ? 'analyzing'
    : workflow?.snapshot.package
      ? 'package'
      : hasAnalysis
        ? 'directions'
        : 'intake'
  const derivedStage: DirectorStageKey = stage === 'intake' || stage === 'analyzing'
    ? 'brief'
    : stage === 'directions'
      ? 'direction'
      : 'package'
  const activeStage = viewedStage ?? derivedStage
  const isLiveDirector = workflow?.mode === 'LIVE_DIRECTOR'
  const stageAvailability: Record<DirectorStageKey, boolean> = {
    brief: true,
    direction: hasAnalysis,
    package: Boolean(workflow?.snapshot.package),
  }
  const progressStages = [
    ['brief', '01', '商品输入'],
    ['direction', '02', '创意方向'],
    ['package', '03', '生产方案'],
  ] as const

  useEffect(() => {
    let active = true
    void getSiteStyleProfiles()
      .then((profiles) => {
        if (active) setBrandProfiles(profiles.filter((profile) => profile.libraryScope === 'brand' && profile.status === 'active'))
      })
      .catch(() => {
        if (active) setBrandProfilesError('品牌目录暂时不可用，可先选择通用风格。')
      })
      .finally(() => {
        if (active) setBrandProfilesLoading(false)
      })
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (!hasAnalysis) return
    const frame = window.requestAnimationFrame(() => {
      directionsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      directionsHeadingRef.current?.focus({ preventScroll: true })
    })
    return () => window.cancelAnimationFrame(frame)
  }, [hasAnalysis])

  const persistPlanningSnapshot = (
    nextWorkflow: DirectorTaskResponse | null,
    nextDraft: DirectorDraft = draft,
  ) => {
    if (!projectContext) return
    const recovery = nextWorkflow
      ? createDirectorTaskRecovery(nextWorkflow, productIdRef.current)
      : null
    const workflowContext = {
      ...projectContext.project.workflowContext,
      ...(nextWorkflow ? {
        activeTaskId: nextWorkflow.id,
        creativeTaskId: nextWorkflow.id,
        planningSnapshotRevision: nextWorkflow.state_version,
        ...(recovery?.product_reference.product_id ? { activeProductId: recovery.product_reference.product_id } : {}),
        ...(recovery?.product_reference.product_version_id ? { activeProductVersionId: recovery.product_reference.product_version_id } : {}),
      } : {}),
      currentStage: nextDraft.phase,
    }
    projectContext.updateProject({
      currentStage: nextDraft.phase === 'package' ? 'production-package' : nextDraft.phase,
      workflowContext,
      metadata: {
        directorPlanning: selectDirectorPlanningSnapshot(
          nextWorkflow,
          nextDraft,
          projectContext.project.id,
          snapshot,
          null,
        ),
        ...(recovery ? { directorRecovery: recovery } : {}),
      },
    })
  }

  const updateIntake = (patch: Partial<DirectorProductIntake>) => {
    const nextDraft = { ...draft, intake: { ...draft.intake, ...patch } }
    setDraft(nextDraft)
    persistPlanningSnapshot(workflow, nextDraft)
    setNotice('')
  }

  const onFrontImage = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    updateIntake({
      productFrontName: file.name,
      productFrontPreviewUrl: URL.createObjectURL(file),
      productFrontFile: file,
    })
  }

  const applyWorkflow = (
    next: DirectorTaskResponse,
    baseDraft: DirectorDraft = draft,
  ) => {
    setViewedStage(null)
    setWorkflow(next)
    if (next.snapshot.brand_dna) setSelectedBrandId(next.snapshot.brand_dna.profileId)
    const nextDraft = {
      ...baseDraft,
      ...(next.snapshot.brand_dna ? { intake: { ...baseDraft.intake, brandMode: 'brand', brandName: next.snapshot.brand_dna.name } } : {}),
      ...({
        phase: next.snapshot.package ? 'package' : next.snapshot.plan ? 'directions' : draft.phase,
        directions: next.snapshot.plan?.directions
          ? directionsFromAnalysis(next.snapshot.plan.directions)
          : baseDraft.directions,
        selectedDirectionId: next.snapshot.plan?.selected_direction ?? baseDraft.selectedDirectionId,
      }),
    } as DirectorDraft
    setDraft((current) => ({
      ...current,
      ...(next.snapshot.brand_dna ? { intake: { ...current.intake, brandMode: 'brand', brandName: next.snapshot.brand_dna.name } } : {}),
      phase: next.snapshot.package ? 'package' : next.snapshot.plan ? 'directions' : current.phase,
      directions: next.snapshot.plan?.directions
        ? directionsFromAnalysis(next.snapshot.plan.directions)
        : current.directions,
      selectedDirectionId: next.snapshot.plan?.selected_direction ?? current.selectedDirectionId,
    }))
    persistPlanningSnapshot(next, nextDraft)
  }

  useEffect(() => {
    const recovery = projectContext ? selectDirectorTaskRecovery(projectContext.project) : null
    if (!recovery || workflow || recoveryAttemptRef.current === recovery.creative_task_id) return
    recoveryAttemptRef.current = recovery.creative_task_id
    const restoredDraft = projectContext
      ? draftFromPersistedDirectorProject(projectContext.project, recovery)
      : createDirectorDraft()
    setDraft(restoredDraft)
    setBusyAction('refresh')
    let active = true
    void getDirectorTask(recovery.creative_task_id)
      .then(async (next) => {
        if (!active) return
        const validation = validateDirectorTaskRecovery(recovery, next)
        if (!validation.valid) {
          projectContext?.clearProjectRecovery()
          setWorkflow(null)
          setDraft(createDirectorDraft())
          setNotice(directorRecoveryMessage(validation.reason ?? 'RECOVERY_REFERENCE_INVALID'))
          return
        }
        if (recovery.product_reference.product_id) {
          const product = await getDirectorProduct(recovery.product_reference.product_id)
          const productValidation = validateDirectorProductReference(recovery, product)
          if (!productValidation.valid) {
            projectContext?.clearProjectRecovery()
            setWorkflow(null)
            setDraft(createDirectorDraft())
            setNotice(directorRecoveryMessage(productValidation.reason ?? 'PRODUCT_VERSION_STALE'))
            return
          }
        }
        applyWorkflow(next, restoredDraft)
        setNotice('已恢复服务端导演任务，审核、选择和当前版本来自服务端。')
      })
      .catch((cause) => {
        if (!active) return
        const kind = classifyDirectorRecoveryError(cause)
        if (kind !== 'NETWORK_ERROR') {
          projectContext?.clearProjectRecovery()
          setWorkflow(null)
          setDraft(createDirectorDraft())
        }
        setNotice(directorRecoveryMessage(kind))
      })
      .finally(() => {
        if (active) setBusyAction(null)
      })
    return () => {
      active = false
    }
  // applyWorkflow intentionally stays local so it can use the current draft/project snapshot.
  // The recovery id guard makes this one-shot effect safe across provider persistence updates.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectContext, workflow])

  const runCommand = async (
    action: DirectorCommandInput['action'],
    payload: Omit<DirectorCommandInput, 'action' | 'expected_version'>,
  ) => {
    if (!workflow) return null
    const fingerprint = JSON.stringify([workflow.id, workflow.state_version, action, payload])
    if (commandRef.current?.fingerprint !== fingerprint) {
      commandRef.current = { fingerprint, key: createUuid() }
    }
    const next = await sendDirectorCommand(workflow.id, {
      ...payload,
      action,
      expected_version: workflow.state_version,
      command_key: commandRef.current.key,
    })
    applyWorkflow(next)
    return next
  }

  const chooseDirection = (direction: DirectorDirection) => {
    if (!workflow || busyAction || directionConfirmed || workflow.status !== 'AWAITING_DIRECTION') return
    setNotice('')
    const nextDraft = selectDirectorDirection(draft, direction.id)
    setDraft(nextDraft)
    persistPlanningSnapshot(workflow, nextDraft)
    setNotice(`已选择 ${direction.id} · ${direction.title}。确认后才会生成生产方案。`)
  }

  const confirmDirection = async () => {
    if (!workflow || !selectedDirection || busyAction || directionConfirmed || workflow.status !== 'AWAITING_DIRECTION') return
    setBusyAction('select')
    setNotice('')
    try {
      await runCommand('select_direction', {
        direction_id: selectedDirection.id,
      })
      setNotice('方向已确认，生产方案已准备。')
    } catch (cause) {
      setNotice(explainDirectorFailure(cause, '方向确认失败，请重试。'))
    } finally {
      setBusyAction(null)
    }
  }

  const requestAnalysis = async () => {
    if (busyAction || (workflow && !canRetryAnalysis)) return
    if (!workflow && (!ready || !draft.intake.productFrontFile)) {
      setNotice('请先上传商品正面图。')
      return
    }
    setBusyAction('analyze')
    setNotice('')
    let current = workflow
    try {
      if (!current) {
        const label = draft.intake.productName.trim()
          || draft.intake.productFrontName.replace(/\.[^.]+$/, '')
          || 'product'
        if (!productIdRef.current) {
          const product = await createDirectorProduct(`director-${label}-${createUuid().slice(0, 8)}`)
          productIdRef.current = product.id
        }
        const created = await createDirectorTask({
          productId: productIdRef.current,
          front: draft.intake.productFrontFile!,
          clientKey: clientKeyRef.current,
          ...(draft.intake.brandMode === 'brand' && chosenBrand ? {
            brandProfileId: chosenBrand.id,
            brandProfileVersion: chosenBrand.version,
          } : {}),
        })
        applyWorkflow(created)
        setRejectionReasons({})
        current = created
      } else {
        current = await getDirectorTask(current.id)
        applyWorkflow(current)
      }
      if (current.status !== 'DRAFT' && current.status !== 'ANALYSIS_FAILED') return
      const action = current.status === 'ANALYSIS_FAILED' ? 'retry_analysis' : 'analyze'
      const fingerprint = JSON.stringify([current.id, current.state_version, action])
      if (commandRef.current?.fingerprint !== fingerprint) {
        commandRef.current = { fingerprint, key: createUuid() }
      }
      const analyzed = await sendDirectorCommand(current.id, {
        action,
        command_key: commandRef.current.key,
        expected_version: current.state_version,
      })
      applyWorkflow(analyzed)
      setNotice('分析完成。请选择 A、B 或 C 方向。')
    } catch (cause) {
      if (current) {
        try { applyWorkflow(await getDirectorTask(current.id)) } catch { /* Preserve the existing recovery reference. */ }
      }
      setNotice(explainDirectorFailure(cause, '创建或分析失败，请检查服务后重试分析。'))
    } finally {
      setBusyAction(null)
    }
  }

  const authorize = async (expiresAt: string, scope: 'FIRST_FRAME' | 'VIDEO_STORYBOARD') => {
    const packageRevision = scope === 'VIDEO_STORYBOARD'
      ? storyboardPackage ?? workflow?.snapshot.package
      : workflow?.snapshot.package
    if (!workflow || !packageRevision || busyAction) return
    if (scope === 'VIDEO_STORYBOARD' && !canAuthorizeStoryboard(workflow)) return
    setBusyAction(scope === 'VIDEO_STORYBOARD' ? 'authorize_storyboard' : 'authorize')
    setNotice('')
    try {
      const fingerprint = JSON.stringify([workflow.id, workflow.state_version, scope])
      if (authorizationRef.current?.fingerprint !== fingerprint) {
        authorizationRef.current = { fingerprint, payload: {
          authorization_id: createUuid(),
          // The backend accepts the root package for storyboard authorization
          // and returns the generated SHOT_01 package in the next snapshot.
          package_id: scope === 'VIDEO_STORYBOARD'
            ? workflow.snapshot.package?.package_id ?? packageRevision.package_id
            : packageRevision.package_id,
          locks_hash: packageRevision.locks_hash,
          scope,
          shot_ids: [scope === 'VIDEO_STORYBOARD' ? 'SHOT_01' : 'FIRST_FRAME'],
          expires_at: expiresAt,
          loop_enabled: false,
          max_revisions: 0,
          max_calls: 6,
          max_cost_micros: 6,
          currency: 'FAKE',
          allowed_modules: ['Reality'],
          ...(workflow.snapshot.authorization ? {
            parent_authorization_id: workflow.snapshot.authorization.authorization_id,
          } : {}),
        } }
      }
      await runCommand('authorize', {
        authorization: authorizationRef.current.payload,
      })
      setNotice(scope === 'VIDEO_STORYBOARD'
        ? '分镜授权已记录。现在可以生成离线 Fake 分镜。'
        : '首帧授权已记录。现在可以生成离线 Fake 首帧。')
    } catch (cause) {
      setNotice(explainDirectorFailure(cause, '授权结果未确认，请刷新任务状态后重试。'))
    } finally {
      setBusyAction(null)
    }
  }

  const generate = async () => {
    const packageRevision = workflow?.snapshot.package
    if (!workflow || !packageRevision || !workflow.snapshot.authorization || busyAction) return
    setBusyAction('generate')
    setNotice('')
    try {
      await runCommand('generate', {
        package_id: packageRevision.package_id,
      })
      setNotice('Fake 首帧已生成。该候选仅用于离线流程验证，不可交付。')
    } catch (cause) {
      setNotice(explainDirectorFailure(cause, 'Fake 首帧生成失败，请重试。'))
    } finally {
      setBusyAction(null)
    }
  }

  const generateStoryboard = async () => {
    if (!workflow || !storyboardPackage || workflow.snapshot.authorization?.scope !== 'VIDEO_STORYBOARD' || busyAction) return
    if (workflow.mode !== 'OFFLINE_FAKE_ONLY' || workflow.status !== 'IMAGE_REVIEW'
      || workflow.snapshot.stopped
      || ['UNKNOWN', 'WRITE_UNCERTAIN'].includes(workflow.snapshot.execution_state ?? '')) return
    setBusyAction('generate_storyboard')
    setNotice('')
    try {
      await runCommand('generate', {
        package_id: storyboardPackage.package_id,
        shot_id: 'SHOT_01',
      })
      setNotice('Fake 分镜已生成。该候选仅用于离线流程验证，不可交付。')
    } catch (cause) {
      setNotice(explainDirectorFailure(cause, 'Fake 分镜生成失败，请重试。'))
    } finally {
      setBusyAction(null)
    }
  }

  const reviewCandidate = async (candidate: DirectorCandidate, decision: 'QUALIFIED' | 'REJECTED') => {
    const canReview = workflow && candidate.shot_id === 'FIRST_FRAME'
      ? canReviewDirectorCandidate(workflow, candidate)
      : workflow
        ? canReviewDirectorStoryboardCandidate(workflow, candidate)
        : false
    if (!workflow || busyAction || !canReview) return
    const reason = rejectionReasons[candidate.candidate_id]?.trim() ?? ''
    if (decision === 'REJECTED' && (!reason || reason.length > 500)) return
    setBusyAction('review')
    setNotice('')
    try {
      await runCommand('review', {
        candidate_id: candidate.candidate_id,
        ...(candidate.shot_id !== 'FIRST_FRAME' ? { shot_id: candidate.shot_id } : {}),
        decision,
        ...(decision === 'REJECTED' ? { reason } : {}),
      })
      setNotice(decision === 'QUALIFIED'
        ? '离线审核决定已记录，可单独选择候选；该 Fake 候选仍不可交付。'
        : '离线拒绝已记录，该候选的选择已撤回。')
    } catch (cause) {
      setNotice(explainDirectorFailure(cause, '审核结果未确认，请刷新任务状态后重试。'))
    } finally {
      setBusyAction(null)
    }
  }

  const selectFirstFrame = async (candidate: DirectorCandidate) => {
    if (!workflow || busyAction || !canSelectDirectorCandidate(workflow, candidate)) return
    setBusyAction('select_frame')
    setNotice('')
    try {
      await runCommand('select', { candidate_id: candidate.candidate_id })
      setNotice('离线首帧选择已记录；不代表真实 QUALIFIED 或可交付素材。')
    } catch (cause) {
      setNotice(explainDirectorFailure(cause, '选择结果未确认，请刷新任务状态后重试。'))
    } finally {
      setBusyAction(null)
    }
  }

  const selectStoryboard = async (candidate: DirectorCandidate) => {
    if (!workflow || busyAction || !canSelectDirectorStoryboardCandidate(workflow, candidate)) return
    setBusyAction('select_storyboard')
    setNotice('')
    try {
      await runCommand('select', {
        candidate_id: candidate.candidate_id,
        shot_id: 'SHOT_01',
      })
      setNotice('离线分镜选择已记录；不代表真实 QUALIFIED 或可交付素材。')
    } catch (cause) {
      setNotice(explainDirectorFailure(cause, '分镜选择未确认，请刷新任务状态后重试。'))
    } finally {
      setBusyAction(null)
    }
  }

  const refreshWorkflow = async () => {
    if (!workflow || busyAction) return
    setBusyAction('refresh')
    setNotice('')
    try {
      const next = await getDirectorTask(workflow.id)
      const recovery = projectContext ? selectDirectorTaskRecovery(projectContext.project) : null
      if (recovery) {
        const validation = validateDirectorTaskRecovery(recovery, next)
        if (!validation.valid) {
          projectContext?.clearProjectRecovery()
          setWorkflow(null)
          setDraft(createDirectorDraft())
          setNotice(directorRecoveryMessage(validation.reason ?? 'RECOVERY_REFERENCE_INVALID'))
          return
        }
        if (recovery.product_reference.product_id) {
          const product = await getDirectorProduct(recovery.product_reference.product_id)
          const productValidation = validateDirectorProductReference(recovery, product)
          if (!productValidation.valid) {
            projectContext?.clearProjectRecovery()
            setWorkflow(null)
            setDraft(createDirectorDraft())
            setNotice(directorRecoveryMessage(productValidation.reason ?? 'PRODUCT_VERSION_STALE'))
            return
          }
        }
      }
      applyWorkflow(next)
      setNotice('已读取服务端状态，审核决定和理由来自最新服务端记录。')
    } catch (cause) {
      setNotice(explainDirectorFailure(cause, '任务状态刷新失败，请重试。'))
    } finally {
      setBusyAction(null)
    }
  }

  return <section className="director-studio page-view" aria-label="智能导演">
    <header className="director-studio__header">
      <div>
        <span className="director-studio__eyebrow">Director Studio</span>
        <h1>导演台</h1>
        <p>从商品输入、创意方向到生产方案。</p>
      </div>
      <span className="director-studio__contract"><LockKeyhole size={14} />{isLiveDirector ? 'Live Director · 仅导演分析' : 'Offline Demo · 不可交付'}</span>
    </header>

    <ol className="director-studio__steps" aria-label="导演创作阶段">
      {progressStages.map(([key, index, label]) => {
        const currentIndex = progressStages.findIndex(([value]) => value === activeStage)
        const itemIndex = progressStages.findIndex(([value]) => value === key)
        const available = stageAvailability[key]
        return <li key={key} className={`${activeStage === key ? 'is-active' : itemIndex < currentIndex ? 'is-done' : ''}${available ? '' : ' is-disabled'}`}>
          <button type="button" disabled={!available} onClick={() => setViewedStage(key)}>
            <span className="director-step-number">{index}</span><strong>{label}</strong>
          </button>
        </li>
      })}
    </ol>

    <div className="director-studio__workspace">
      <section className={`director-stage director-stage--brief${activeStage === 'brief' ? ' is-active' : ' is-secondary'}`} aria-labelledby="director-intake-title">
        <div className="director-stage__summary">
          <strong>商品输入</strong>
          <span>{draft.intake.productFrontName ? `${draft.intake.productFrontName}${draft.intake.brandName ? ` · ${draft.intake.brandName}` : ''}` : '上传商品正面图并选择品牌归属'}</span>
        </div>
        <div className="director-stage__content">
        <section className="director-panel director-panel--intake">
        <div className="director-panel__heading">
          <div><span className="director-panel__index">01</span><div><h2 id="director-intake-title">商品输入 <small>Product Brief</small></h2><p>商品正面是最低输入，品牌归属用于约束创意方向。</p></div></div>
          <span className={ready ? 'director-state is-ready' : 'director-state'}>{ready ? '已就绪' : '待输入'}</span>
        </div>
        <div className="director-intake-layout">
          <div className="director-intake-primary">
            <ImageUploadTrigger className="director-upload" title={draft.intake.productFrontPreviewUrl ? '更换商品正面' : '上传商品正面'}
              disabled={workflow !== null || busyAction !== null} onClick={() => frontImageInputRef.current?.click()}
              preview={draft.intake.productFrontPreviewUrl ? <img src={draft.intake.productFrontPreviewUrl} alt="商品正面预览" /> : undefined} />
            <input ref={frontImageInputRef} hidden type="file" accept="image/*" onChange={onFrontImage} disabled={workflow !== null || busyAction !== null} />
            {draft.intake.productFrontName ? <p className="director-file-name">{draft.intake.productFrontName}</p> : null}
            <div className="director-media-mode director-media-mode--secondary" role="group" aria-label="分析素材类型">
              <span>输入类型</span>
              <button type="button" className="is-selected" aria-pressed="true"><FileImage size={15} />图片</button>
              <button type="button" disabled title="当前导演分析接口仅支持图片">视频<span>即将支持</span></button>
            </div>
          </div>
          <div className="director-intake-fields">
            <fieldset className="director-choice">
              <legend>品牌归属 <small>已生效输入 · 必选</small></legend>
              <label><input type="radio" disabled={Boolean(workflow)} checked={draft.intake.brandMode === 'generic'} onChange={() => { setSelectedBrandId(''); updateIntake({ brandMode: 'generic', brandName: '' }) }} />通用风格</label>
              <label><input type="radio" disabled={Boolean(workflow)} checked={draft.intake.brandMode === 'brand'} onChange={() => updateIntake({ brandMode: 'brand' })} />选择品牌</label>
            </fieldset>
            {draft.intake.brandMode === 'brand' ? <label className="director-field"><span>品牌 <small>必选</small></span><select value={chosenBrand?.id ?? workflow?.snapshot.brand_dna?.profileId ?? ''} disabled={brandProfilesLoading || Boolean(workflow)} onChange={(event) => { setSelectedBrandId(event.target.value); updateIntake({ brandName: brandProfiles.find(profile => profile.id === event.target.value)?.name ?? '' }) }}><option value="">{brandProfilesLoading ? '正在读取品牌目录' : '请选择已确认品牌'}</option>{workflow?.snapshot.brand_dna && !chosenBrand ? <option value={workflow.snapshot.brand_dna.profileId}>{workflow.snapshot.brand_dna.name} · {workflow.snapshot.brand_dna.profileVersion}</option> : null}{brandProfiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.name} · {profile.version}</option>)}</select></label> : null}
            {draft.intake.brandMode === 'brand' ? <DirectorBrandDNAView profile={chosenBrand} snapshot={workflow?.snapshot.brand_dna} /> : null}
            {brandProfilesError && draft.intake.brandMode === 'brand' ? <p className="director-inline-note is-warning">{brandProfilesError}</p> : null}
          </div>
        </div>
        <details className="director-brief-details">
          <summary>高级创作设置 <small>计划支持</small></summary>
          <p id="director-planned-input-note" className="director-inline-note">仅记录创作意向，尚未接入分析；不会影响当前创意方向或图片、视频 Prompt。</p>
          <div className="director-intake-options" aria-describedby="director-planned-input-note">
            <label className="director-field"><span>产品材质 <small>计划支持</small></span><input value={draft.intake.material} onChange={(event) => updateIntake({ material: event.target.value })} placeholder="例如：棉、亚麻" /></label>
            <label className="director-field"><span>视频类型 <small>计划支持</small></span><select value={draft.intake.videoType} onChange={(event) => updateIntake({ videoType: event.target.value })}><option value="">未指定</option><option value="product">商品展示</option><option value="lifestyle">生活方式</option><option value="ugc">UGC</option></select></label>
            <label className="director-field"><span>模特性别 <small>计划支持</small></span><select value={draft.intake.modelGender ?? ''} onChange={(event) => updateIntake({ modelGender: event.target.value })}><option value="">未指定</option><option value="female">女性</option><option value="male">男性</option><option value="unspecified">不限</option></select></label>
            <label className="director-field"><span>模特年龄范围 <small>计划支持</small></span><input value={draft.intake.modelAgeRange ?? ''} onChange={(event) => updateIntake({ modelAgeRange: event.target.value })} placeholder="例如：25–35 岁" /></label>
            <label className="director-field"><span>视频时长 <small>计划支持 · 秒</small></span><input type="number" min={1} step={1} value={draft.intake.videoDurationSeconds ?? ''} onChange={(event) => updateIntake({ videoDurationSeconds: Number.isFinite(event.target.valueAsNumber) && event.target.valueAsNumber > 0 ? event.target.valueAsNumber : undefined })} placeholder="未指定" /></label>
            <label className="director-field"><span>视频比例 <small>计划支持</small></span><select value={draft.intake.videoAspectRatio ?? ''} onChange={(event) => updateIntake({ videoAspectRatio: event.target.value })}><option value="">未指定</option><option value="9:16">9:16</option><option value="16:9">16:9</option><option value="1:1">1:1</option></select></label>
            <label className="director-field director-field--wide"><span>创作备注 <small>计划支持</small></span><textarea rows={3} value={draft.intake.notes} onChange={(event) => updateIntake({ notes: event.target.value })} placeholder="记录希望保留的细节或创作限制" /></label>
          </div>
        </details>
        <div className="director-brief-cta">
          <button type="button" className="primary-button director-action" onClick={() => void requestAnalysis()} disabled={busyAction !== null || (workflow ? !canRetryAnalysis : !ready)}>
            <WandSparkles size={16} />{busyAction === 'analyze' ? '正在生成创意方向' : canRetryAnalysis ? '重试分析' : workflow ? '已生成创意方向' : '生成创意方向'}
          </button>
        </div>
      </section>
        </div>
      </section>

      <section className={`director-stage director-stage--direction${activeStage === 'direction' ? ' is-active' : ' is-secondary'}`} aria-labelledby="director-directions-title">
        <div className="director-stage__summary">
          <strong>创意方向</strong>
          <span>{hasAnalysis ? `${draft.directions.length} 个候选方向${selectedDirection ? ` · 已选择 ${selectedDirection.id}` : ''}` : '完成商品输入后生成创意方向'}</span>
        </div>
        <div className="director-stage__content">
      {hasAnalysis ? <section ref={directionsRef} className="director-panel director-panel--directions" aria-labelledby="director-directions-title">
        <div className="director-panel__heading">
          <div><span className="director-panel__index">02</span><div><h2 ref={directionsHeadingRef} id="director-directions-title" tabIndex={-1}>创意方向 <small>Creative Direction</small></h2><p>基于商品理解生成候选方向，选择后再进入生产包。</p></div></div>
          <span className="director-state">{workflow?.snapshot.plan ? `${draft.directions.length} 个候选` : '等待分析'}</span>
        </div>
        <div className="director-direction-workspace">
          <div className="director-direction-list">
            {draft.directions.map((direction) => <DirectorDirectionCard
              key={direction.id}
              direction={direction}
              workflow={workflow}
              selected={draft.selectedDirectionId === direction.id}
              confirmed={confirmedDirectionId === direction.id}
              onSelect={() => chooseDirection(direction)}
              disabled={!workflow || workflow.status !== 'AWAITING_DIRECTION' || busyAction !== null || directionConfirmed}
            />)}
          </div>
          <div className="director-direction-actions">
            <button
              type="button"
              className="primary-button director-action director-direction-confirm"
              onClick={() => void confirmDirection()}
              disabled={!selectedDirection || directionConfirmed || busyAction !== null || workflow?.status !== 'AWAITING_DIRECTION'}
            >
              <Check size={16} />
              {busyAction === 'select'
                ? '正在确认方向'
                : directionConfirmed
                  ? '方向已确认'
                  : selectedDirection
                    ? `确认方向：${selectedDirection.id} · ${selectedDirection.title}`
                    : '请选择一个方向'}
            </button>
          </div>
        </div>
      </section> : <div className="director-stage__empty">上传商品并点击“生成创意方向”后，这里会显示产品理解摘要和候选方向。</div>}
        </div>
      </section>

      <section className={`director-stage director-stage--package${activeStage === 'package' ? ' is-active' : ' is-secondary'}`} aria-labelledby="director-package-title">
        <div className="director-stage__summary">
          <strong>生产方案</strong>
          <span>{workflow?.snapshot.package ? packageState : '确认方向后整理图片提示词、视频创作提案和镜头规划'}</span>
        </div>
        <div className="director-stage__content">
      {workflow?.snapshot.package ? <section className="director-panel director-panel--package" aria-labelledby="director-package-title">
        <div className="director-panel__heading"><div><span className="director-panel__index">03</span><div><h2 id="director-package-title">生产方案 <small>Production Package</small></h2><p>创意交接文档</p></div></div></div>
        <section className="director-handoff-summary" aria-label="当前方案摘要">
          <h3>当前方案摘要</h3>
          <dl className="director-handoff-summary__facts">
            <div><dt>已确认方向</dt><dd>{confirmedDirectionId ? `${confirmedDirectionId}${selectedDirection ? ` · ${selectedDirection.title}` : ''}` : '未提供'}</dd></div>
            <div><dt>方案版本</dt><dd>r{workflow.snapshot.package.revision} · 首帧图片规划</dd></div>
          </dl>
          {selectedDirection ? <p className="director-handoff-summary__description">{selectedDirection.summary}<small>方向结果整理 · 名称为本地创意提案</small></p> : null}
          <div className="director-package-state"><LockKeyhole size={18} /><div><strong>Fake · 仅规划 · 不可交付</strong><span>{packageState}；不代表素材已生成或已验证生产内容。</span></div></div>
        </section>
        <CreativePackageExportView workflow={workflow} packageId={workflow.snapshot.package.package_id}>
         <DirectorAnalysisTrace analysis={workflow.snapshot.director_analysis} />
        <dl className="director-package-list">
          <div><dt>商品事实</dt><dd>{ready ? '正面已提供' : '未提供'}</dd></div>
          <div><dt>方向选择</dt><dd>{selectedDirection ? selectedDirection.id : '未选择'}</dd></div>
          <div><dt>任务状态</dt><dd>{workflow?.status ?? '未创建'}</dd></div>
        </dl>
        {workflow ? <div className="director-task-toolbar">
          <span>版本 {workflow.state_version} · {workflow.snapshot.execution_state ?? '暂无执行证据'}</span>
          <button type="button" className="secondary-button" onClick={() => void refreshWorkflow()} disabled={busyAction !== null}>
            <RefreshCw size={16} />{busyAction === 'refresh' ? '正在刷新' : '刷新任务状态'}
          </button>
        </div> : null}
        <DirectorPackageEvidence workflow={workflow} shotId="FIRST_FRAME" />
        {workflow?.mode === 'OFFLINE_FAKE_ONLY' && workflow?.snapshot.package && !firstFrameCandidates.length ? <div className="director-package-actions">
          {!workflow.snapshot.authorization ? <button type="button" className="primary-button director-action" onClick={() => {
            const expiresAt = new Date()
            expiresAt.setTime(expiresAt.getTime() + 60 * 60 * 1000)
            void authorize(expiresAt.toISOString(), 'FIRST_FRAME')
          }} disabled={busyAction !== null}>
            <LockKeyhole size={16} />{busyAction === 'authorize' ? '正在记录授权' : '授权 Fake 首帧'}
          </button> : <button type="button" className="primary-button director-action" onClick={() => void generate()} disabled={busyAction !== null}>
            <WandSparkles size={16} />{busyAction === 'generate' ? '正在生成 Fake 首帧' : '生成 Fake 首帧'}
          </button>}
        </div> : null}
        {workflow && firstFrameCandidates.length ? <section aria-label="首帧候选审核">
          {firstFrameCandidates.map((candidate, index) => {
            if (!workflow) return null
            const selected = workflow.snapshot.selection?.candidate_id === candidate.candidate_id
            const canReview = canReviewDirectorCandidate(workflow, candidate)
            const reason = rejectionReasons[candidate.candidate_id] ?? ''
            const latestReview = workflow.snapshot.latest_review?.candidate_id === candidate.candidate_id
              ? workflow.snapshot.latest_review
              : undefined
            const reviewLabel = latestReview?.decision === 'QUALIFIED'
              ? '服务端审核：合格（仅离线范围）'
              : latestReview?.decision === 'REJECTED'
                ? '服务端审核：已拒绝'
                : candidate.qualified
                  ? '离线审核：合格（仅流程决定）'
                  : '离线审核：待人工审核'
            return <section key={candidate.candidate_id} className="director-candidate" aria-label={`首帧候选 ${index + 1}`} style={{ marginTop: 16, overflowWrap: 'anywhere' }}>
              <div className="director-candidate__heading"><strong>首帧候选 {index + 1}</strong><p>OFFLINE_SYNTHETIC_ONLY · 不可交付</p></div>
              {draft.intake.productFrontPreviewUrl
                ? <img src={draft.intake.productFrontPreviewUrl} alt="离线 Fake 首帧占位，沿用商品正面图" style={{ width: '100%', maxHeight: 280, objectFit: 'contain' }} />
                : <div role="img" aria-label="商品正面由服务端引用恢复" style={{ minHeight: 180, display: 'grid', placeItems: 'center', color: 'var(--muted)' }}>商品正面已由服务端引用恢复</div>}
              <p>候选 ID：{candidate.candidate_id}</p>
              <p role="status">{reviewLabel}</p>
              <p>{selected ? '首帧选择：已选择（仅离线）' : '首帧选择：未选择'}</p>
              <small>Fake 候选不具备真实 QUALIFIED / Deliverable 资格。</small>
              <label className="director-field">
                <span>拒绝理由（必填，最多 500 字）</span>
                <textarea rows={2} maxLength={500} value={reason} disabled={!canReview || busyAction !== null}
                  onChange={(event) => setRejectionReasons((current) => ({ ...current, [candidate.candidate_id]: event.target.value }))} />
              </label>
              {latestReview?.decision === 'REJECTED' && latestReview.reason
                ? <p>服务端拒绝理由：{latestReview.reason}</p>
                : null}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
                <button type="button" className="secondary-button" disabled={!canReview || busyAction !== null || candidate.qualified} onClick={() => void reviewCandidate(candidate, 'QUALIFIED')}>
                  <Check size={16} />离线审核合格
                </button>
                <button type="button" className="secondary-button" disabled={!canReview || busyAction !== null || !reason.trim() || reason.trim().length > 500} onClick={() => void reviewCandidate(candidate, 'REJECTED')}>
                  <X size={16} />拒绝候选
                </button>
                <button type="button" className="primary-button" disabled={!canSelectDirectorCandidate(workflow, candidate) || busyAction !== null || selected} onClick={() => void selectFirstFrame(candidate)}>
                  <Check size={16} />{selected ? '已选择离线首帧' : '选择离线首帧'}
                </button>
              </div>
              <HumanReviewPanel subjectType="DIRECTOR_CANDIDATE" subjectId={candidate.candidate_id} taskId={workflow.id} />
            </section>
          })}
        </section> : null}
        <section className="director-storyboard" aria-labelledby="director-storyboard-title">
          <div className="director-panel__heading">
            <div>
              <span className="director-panel__index">04</span>
              <div>
                <h2 id="director-storyboard-title">镜头规划验证 / SHOT_01</h2>
                <p>首帧选择后，单独处理 SHOT_01。</p>
              </div>
            </div>
            <span className="director-state">
              {storyboardCandidates.length
                ? `${storyboardCandidates.length} 个候选`
                : storyboardPackage
                  ? '已准备'
                  : '等待首帧选择'}
            </span>
          </div>
          <div className="director-package-state">
            <LockKeyhole size={18} />
            <div>
              <strong>{storyboardPackage ? 'SHOT_01 分镜包已建立' : 'SHOT_01 分镜包未建立'}</strong>
              <span>Fake 分镜仅用于验证 workflow，不可用于视频生产或交付。</span>
            </div>
          </div>
          <DirectorPackageEvidence workflow={workflow} shotId="SHOT_01" />
          {storyboardPackage ? <CreativePackageExportView workflow={workflow} packageId={storyboardPackage.package_id} /> : null}
          {workflow && canAuthorizeStoryboard(workflow) ? <button
            type="button"
            className="primary-button director-action"
            onClick={() => {
              const expiresAt = new Date()
              expiresAt.setTime(expiresAt.getTime() + 60 * 60 * 1000)
              void authorize(expiresAt.toISOString(), 'VIDEO_STORYBOARD')
            }}
            disabled={busyAction !== null}
          >
            <LockKeyhole size={16} />{busyAction === 'authorize_storyboard' ? '正在记录分镜授权' : '授权 Fake 分镜'}
          </button> : null}
          {storyboardPackage && workflow?.status === 'IMAGE_REVIEW' && !workflow.snapshot.stopped && !['UNKNOWN', 'WRITE_UNCERTAIN'].includes(workflow.snapshot.execution_state ?? '') && workflow.snapshot.authorization?.scope === 'VIDEO_STORYBOARD' && !storyboardCandidates.length ? <button
            type="button"
            className="primary-button director-action"
            onClick={() => void generateStoryboard()}
            disabled={busyAction !== null}
          >
            <WandSparkles size={16} />{busyAction === 'generate_storyboard' ? '正在生成 Fake 分镜' : '生成 Fake 分镜'}
          </button> : null}
          {storyboardCandidates.length ? <div className="director-storyboard__candidates">
            <p className="director-storyboard__status" role="status">
              {storyboardReview?.decision === 'QUALIFIED'
                ? '服务端审核：合格（仅离线范围）'
                : storyboardReview?.decision === 'REJECTED'
                  ? '服务端审核：已拒绝'
                  : '离线审核：待人工审核'}
              {storyboardSelection ? ' · SHOT_01 已选择' : ' · SHOT_01 未选择'}
            </p>
            {storyboardCandidates.map((candidate, index) => {
              const selected = storyboardSelection?.candidate_id === candidate.candidate_id
              const latestReview = storyboardReview?.candidate_id === candidate.candidate_id ? storyboardReview : null
              const canReview = workflow ? canReviewDirectorStoryboardCandidate(workflow, candidate) : false
              const reason = rejectionReasons[candidate.candidate_id] ?? ''
              return <section key={candidate.candidate_id} className="director-candidate" aria-label={`分镜候选 ${index + 1}`} style={{ marginTop: 16, overflowWrap: 'anywhere' }}>
                <div className="director-candidate__heading"><strong>SHOT_01 分镜候选 {index + 1}</strong><p>OFFLINE_SYNTHETIC_ONLY · 不可交付</p></div>
                {draft.intake.productFrontPreviewUrl
                  ? <img src={draft.intake.productFrontPreviewUrl} alt="离线 Fake 分镜占位，沿用商品正面图" style={{ width: '100%', maxHeight: 280, objectFit: 'contain' }} />
                  : <div role="img" aria-label="商品正面由服务端引用恢复" style={{ minHeight: 180, display: 'grid', placeItems: 'center', color: 'var(--muted)' }}>商品正面已由服务端引用恢复</div>}
                <p>候选 ID：{candidate.candidate_id}</p>
                <p>{selected ? '分镜选择：已选择（仅离线）' : '分镜选择：未选择'}</p>
                {latestReview?.decision === 'REJECTED' && latestReview.reason
                  ? <p>服务端拒绝理由：{latestReview.reason}</p>
                  : null}
                <small>Fake 候选不具备真实 QUALIFIED / Deliverable 资格。</small>
                <label className="director-field">
                  <span>拒绝理由（必填，最多 500 字）</span>
                  <textarea rows={2} maxLength={500} value={reason} disabled={!canReview || busyAction !== null}
                    onChange={(event) => setRejectionReasons((current) => ({ ...current, [candidate.candidate_id]: event.target.value }))} />
                </label>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
                  <button type="button" className="secondary-button" disabled={!canReview || busyAction !== null || candidate.qualified} onClick={() => void reviewCandidate(candidate, 'QUALIFIED')}>
                    <Check size={16} />离线审核合格
                  </button>
                  <button type="button" className="secondary-button" disabled={!canReview || busyAction !== null || !reason.trim() || reason.trim().length > 500} onClick={() => void reviewCandidate(candidate, 'REJECTED')}>
                    <X size={16} />拒绝候选
                  </button>
                  <button type="button" className="primary-button" disabled={!workflow || !canSelectDirectorStoryboardCandidate(workflow, candidate) || busyAction !== null || selected} onClick={() => void selectStoryboard(candidate)}>
                    <Check size={16} />{selected ? '已选择离线分镜' : '选择离线分镜'}
                  </button>
                </div>
                {workflow ? <HumanReviewPanel subjectType="DIRECTOR_CANDIDATE" subjectId={candidate.candidate_id} taskId={workflow.id} /> : null}
              </section>
            })}
          </div> : null}
        </section>
        <section className="director-storyboard" aria-labelledby="director-bridge-title">
          <div className="director-panel__heading">
            <div>
              <span className="director-panel__index">05</span>
              <div>
                <h2 id="director-bridge-title">Production Bridge Preparation</h2>
                <p>查看提交前的只读校验边界。</p>
              </div>
            </div>
            <span className="director-state">{bridgePreparation?.status ?? '等待 handoff'}</span>
          </div>
          {bridgePreparation ? <div className="director-package-state">
            <LockKeyhole size={18} />
            <div>
              <strong>只读桥接上下文 · Provider submission disabled</strong>
              <span>提交前会再次校验 package、授权、来源、许可和预算。</span>
            </div>
          </div> : <p className="director-storyboard__status">完成首帧生产包和方向选择后，才会生成桥接准备上下文。</p>}
          {bridgePreparation ? <dl className="director-package-list">
            <div><dt>Package</dt><dd>{bridgePreparation.packageId} · r{bridgePreparation.packageRevision}</dd></div>
            <div><dt>Shot</dt><dd>{bridgePreparation.shotId}</dd></div>
            <div><dt>提交状态</dt><dd>禁止 Provider submission</dd></div>
          </dl> : null}
          {bridgePreparation ? <div className="director-bridge-readiness" aria-label="Production Bridge readiness">
            <div className="director-bridge-readiness__heading">
              <div>
                <strong>Preflight readiness</strong>
                <span>只读技术证据评分，不代表生产就绪或提交授权</span>
              </div>
              <b>{bridgePreparation.preflight.readiness.score}%</b>
            </div>
            <div className="director-bridge-readiness__track" aria-hidden="true">
              <span style={{ width: `${bridgePreparation.preflight.readiness.score}%` }} />
            </div>
            <div className="director-bridge-readiness__meta">
              <span>{bridgePreparation.preflight.readiness.validatedChecks}/{bridgePreparation.preflight.readiness.totalChecks} 项服务端证据已验证</span>
              <span>{bridgePreparation.preflight.approvalCheckpoint.id} · {bridgePreparation.preflight.approvalCheckpoint.status}</span>
            </div>
            <ul className="director-bridge-reasons">
              {bridgePreparation.blockingReasons.map((reason) => <li key={reason.code}>
                <span className="director-bridge-reason__category">{reason.category}</span>
                <span>{reason.message}</span>
              </li>)}
            </ul>
          </div> : null}
          <DirectorBridgeStatus preparation={bridgePreparation} workflow={workflow} />
        </section>
        {evidence ? <section className="director-storyboard" aria-labelledby="director-evidence-title">
          <div className="director-panel__heading">
            <div>
              <span className="director-panel__index">06</span>
              <div>
                <h2 id="director-evidence-title">Evidence Summary</h2>
                <p>查看事实、Reality 与 Prompt 版本证据。</p>
              </div>
            </div>
            <span className="director-state">只读证据</span>
          </div>
          <dl className="director-package-list">
            <div><dt>Canonical Product</dt><dd><code>{evidence.canonicalProduct.sourceHash ?? '未提供源哈希'}</code></dd></div>
            <div><dt>背面状态</dt><dd>{evidence.backAssumption.value} · {evidence.backAssumption.availability === 'available' ? '已有记录' : '未核验'}</dd></div>
            <div><dt>Grounded Claims</dt><dd>{evidence.groundedClaims.length ? `${evidence.groundedClaims.length} 条事实声明` : '未提供'}</dd></div>
            <div><dt>Prompt / Preservation</dt><dd>{evidence.textPackage.availability === 'available' ? '已提供版本化摘要' : '证据不完整'}</dd></div>
          </dl>
          <details className="technical-details">
            <summary><span>查看 Reality 六维与哈希</span><RefreshCw size={16} /></summary>
            <div>
              <ul className="director-bridge-reasons">
                {evidence.reality.map((item) => <li key={item.dimension}>
                  <span className="director-bridge-reason__category">{item.dimension}</span>
                  <span>{item.decision || '未提供'} · {item.evidence || '未提供证据'}</span>
                </li>)}
              </ul>
              <dl className="director-package-list">
                <div><dt>locks hash</dt><dd><code>{evidence.textPackage.locksHash ?? '未提供'}</code></dd></div>
                <div><dt>preservation hash</dt><dd><code>{evidence.textPackage.preservationHash ?? '未提供'}</code></dd></div>
                <div><dt>contract / registry</dt><dd>{evidence.textPackage.contractHash ?? '未提供'}{evidence.textPackage.registryVersion === null ? '' : ` · v${evidence.textPackage.registryVersion}`}</dd></div>
              </dl>
            </div>
          </details>
        </section> : null}
        </CreativePackageExportView>
      </section> : <div className="director-stage__empty">方向确认后，这里会展示生产方案及其复制、导出入口。</div>}
        </div>
      </section>
    </div>
    {notice ? <div className="director-notice" role="status">{notice}</div> : null}
  </section>
}
