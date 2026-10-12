import { Check, FileImage, LockKeyhole, RefreshCw, Sparkles, WandSparkles, X } from 'lucide-react'
import { useMemo, useRef, useState, type ChangeEvent } from 'react'
import { useOptionalCreativeProject } from '../../creative-project/hooks'
import type { CreativeIntelligenceSnapshot } from '../../creative-project/types'
import { createUuid } from '../../uuid'
import {
  createDirectorProduct,
  createDirectorTask,
  DirectorApiError,
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
} from './directorSelectors'
import { prepareProductionBridge } from './productionBridge'
import './directorStudio.css'

function updateProjectSnapshot(
  snapshot: CreativeIntelligenceSnapshot | undefined,
): CreativeIntelligenceSnapshot | undefined {
  return snapshot
}

export function DirectorStudio() {
  const projectContext = useOptionalCreativeProject()
  const [draft, setDraft] = useState<DirectorDraft>(createDirectorDraft)
  const [workflow, setWorkflow] = useState<DirectorTaskResponse | null>(null)
  const [busyAction, setBusyAction] = useState<'analyze' | 'select' | 'authorize' | 'generate' | 'authorize_storyboard' | 'generate_storyboard' | 'review' | 'select_frame' | 'select_storyboard' | 'refresh' | null>(null)
  const [rejectionReasons, setRejectionReasons] = useState<Record<string, string>>({})
  const [notice, setNotice] = useState('')
  const clientKeyRef = useRef(createUuid())
  const commandRef = useRef<{ fingerprint: string; key: string } | null>(null)
  const authorizationRef = useRef<{
    fingerprint: string
    payload: NonNullable<DirectorCommandInput['authorization']>
  } | null>(null)
  const ready = isDirectorIntakeReady(draft.intake)
  const selectedDirection = draft.directions.find((direction) => direction.id === draft.selectedDirectionId) ?? null
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
    : selectedDirection ? '方向已选择，等待授权' : '选择方向后生成生产包预览'
  const snapshot = useMemo(
    () => updateProjectSnapshot(projectContext?.project.intelligenceSnapshot),
    [projectContext?.project.intelligenceSnapshot],
  )
  const bridgePreparation = prepareProductionBridge(
    workflow ? selectDirectorPlanningSnapshot(workflow, draft, projectContext?.project.id, snapshot).handoff : null,
  )

  const persistPlanningSnapshot = (nextWorkflow: DirectorTaskResponse | null, nextDraft: DirectorDraft = draft) => {
    if (!projectContext) return
    projectContext.updateProject({
      currentStage: nextDraft.phase === 'package' ? 'production-package' : nextDraft.phase,
      metadata: {
        directorPlanning: selectDirectorPlanningSnapshot(
          nextWorkflow,
          nextDraft,
          projectContext.project.id,
          snapshot,
        ),
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

  const applyWorkflow = (next: DirectorTaskResponse) => {
    setWorkflow(next)
    const nextDraft = {
      ...draft,
      ...({
        phase: next.snapshot.package ? 'package' : next.snapshot.plan ? 'directions' : draft.phase,
        directions: next.snapshot.plan?.directions
          ? directionsFromAnalysis(next.snapshot.plan.directions)
          : draft.directions,
        selectedDirectionId: next.snapshot.plan?.selected_direction ?? draft.selectedDirectionId,
      }),
    } as DirectorDraft
    setDraft((current) => ({
      ...current,
      phase: next.snapshot.package ? 'package' : next.snapshot.plan ? 'directions' : current.phase,
      directions: next.snapshot.plan?.directions
        ? directionsFromAnalysis(next.snapshot.plan.directions)
        : current.directions,
      selectedDirectionId: next.snapshot.plan?.selected_direction ?? current.selectedDirectionId,
    }))
    persistPlanningSnapshot(next, nextDraft)
  }

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

  const chooseDirection = async (direction: DirectorDirection) => {
    if (!workflow || busyAction || workflow.status !== 'AWAITING_DIRECTION') return
    setBusyAction('select')
    setNotice('')
    try {
      const nextDraft = selectDirectorDirection(draft, direction.id)
      const nextWorkflow = await runCommand('select_direction', {
        direction_id: direction.id,
      })
      setDraft(nextDraft)
      persistPlanningSnapshot(nextWorkflow, nextDraft)
      projectContext?.updateProject({
        currentStage: 'AWAITING_DIRECTION',
        metadata: {
          directorDirectionId: direction.id,
          directorBrandMode: nextDraft.intake.brandMode,
        },
      })
      setNotice('方向已记录。接下来需要明确授权后才能生成首帧。')
    } catch (cause) {
      setNotice(cause instanceof DirectorApiError ? cause.message : '方向选择失败，请重试。')
    } finally {
      setBusyAction(null)
    }
  }

  const requestAnalysis = async () => {
    if (workflow) return
    if (!ready || !draft.intake.productFrontFile || busyAction) {
      setNotice('请先上传商品正面图。')
      return
    }
    setBusyAction('analyze')
    setNotice('')
    try {
      const label = draft.intake.productName.trim()
        || draft.intake.productFrontName.replace(/\.[^.]+$/, '')
        || 'product'
      const product = await createDirectorProduct(`director-${label}-${createUuid().slice(0, 8)}`)
      const created = await createDirectorTask({
        productId: product.id,
        front: draft.intake.productFrontFile,
        clientKey: clientKeyRef.current,
      })
      applyWorkflow(created)
      setRejectionReasons({})
      const analyzed = await sendDirectorCommand(created.id, {
        action: 'analyze',
        expected_version: created.state_version,
      })
      applyWorkflow(analyzed)
      setNotice('分析完成。请选择 A、B 或 C 方向。')
    } catch (cause) {
      setNotice(cause instanceof DirectorApiError ? cause.message : '创建或分析失败，请检查离线服务。')
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
      setNotice(cause instanceof DirectorApiError ? cause.message : '授权结果未确认，请刷新任务状态后重试。')
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
      setNotice(cause instanceof DirectorApiError ? cause.message : 'Fake 首帧生成失败，请重试。')
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
      setNotice(cause instanceof DirectorApiError ? cause.message : 'Fake 分镜生成失败，请重试。')
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
      setNotice(cause instanceof DirectorApiError ? cause.message : '审核结果未确认，请刷新任务状态后重试。')
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
      setNotice(cause instanceof DirectorApiError ? cause.message : '选择结果未确认，请刷新任务状态后重试。')
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
      setNotice(cause instanceof DirectorApiError ? cause.message : '分镜选择未确认，请刷新任务状态后重试。')
    } finally {
      setBusyAction(null)
    }
  }

  const refreshWorkflow = async () => {
    if (!workflow || busyAction) return
    setBusyAction('refresh')
    setNotice('')
    try {
      applyWorkflow(await getDirectorTask(workflow.id))
      setNotice('已读取服务端状态，审核决定和理由来自最新服务端记录。')
    } catch (cause) {
      setNotice(cause instanceof DirectorApiError ? cause.message : '任务状态刷新失败，请重试。')
    } finally {
      setBusyAction(null)
    }
  }

  return <section className="director-studio page-view" aria-label="智能导演">
    <header className="director-studio__header">
      <div>
        <span className="director-studio__eyebrow"><Sparkles size={14} />Image Studio / Director</span>
        <h1>智能导演</h1>
        <p>从真实商品输入开始，整理方向、锁定判断，再交给现有生产流程执行。</p>
      </div>
      <span className="director-studio__contract"><LockKeyhole size={14} />离线 Fake 模式 · 不可交付</span>
    </header>

    <div className="director-studio__steps" aria-label="导演流程">
      <span className={draft.phase === 'intake' ? 'is-active' : 'is-done'}>01 商品输入</span>
      <span className={draft.phase === 'directions' ? 'is-active' : draft.phase === 'package' ? 'is-done' : ''}>02 方向候选</span>
      <span className={draft.phase === 'package' ? 'is-active' : ''}>03 生产包</span>
    </div>

    <div className="director-studio__grid">
      <section className="director-panel director-panel--intake" aria-labelledby="director-intake-title">
        <div className="director-panel__heading">
          <div><span className="director-panel__index">01</span><div><h2 id="director-intake-title">Product Intake</h2><p>商品正面是最低输入，背面和详情图后续按合同补充。</p></div></div>
          <span className={ready ? 'director-state is-ready' : 'director-state'}>{ready ? '已就绪' : '待输入'}</span>
        </div>
        <label className="director-upload">
          <input type="file" accept="image/*" onChange={onFrontImage} disabled={workflow !== null || busyAction !== null} />
          {draft.intake.productFrontPreviewUrl
            ? <img src={draft.intake.productFrontPreviewUrl} alt="商品正面预览" />
            : <><FileImage size={24} /><strong>上传商品正面</strong><small>PNG、JPG 或 WEBP</small></>}
        </label>
        {draft.intake.productFrontName ? <p className="director-file-name">{draft.intake.productFrontName}</p> : null}
        <label className="director-field"><span>商品名称</span><input value={draft.intake.productName} onChange={(event) => updateIntake({ productName: event.target.value })} placeholder="例如：棉质短款外套" /></label>
        <fieldset className="director-choice">
          <legend>品牌来源</legend>
          <label><input type="radio" checked={draft.intake.brandMode === 'generic'} onChange={() => updateIntake({ brandMode: 'generic', brandName: '' })} />通用风格</label>
          <label><input type="radio" checked={draft.intake.brandMode === 'brand'} onChange={() => updateIntake({ brandMode: 'brand' })} />选择品牌</label>
        </fieldset>
        {draft.intake.brandMode === 'brand' ? <label className="director-field"><span>品牌名称</span><input value={draft.intake.brandName} onChange={(event) => updateIntake({ brandName: event.target.value })} placeholder="输入已确认的品牌" /></label> : null}
        <label className="director-field"><span>创作目标 <small>可选</small></span><input value={draft.intake.objective} onChange={(event) => updateIntake({ objective: event.target.value })} placeholder="例如：突出面料质感和日常穿着场景" /></label>
        <label className="director-field"><span>目标受众 <small>可选</small></span><input value={draft.intake.audience} onChange={(event) => updateIntake({ audience: event.target.value })} placeholder="例如：关注通勤穿搭的成年用户" /></label>
        <label className="director-field"><span>创作备注 <small>可选</small></span><textarea value={draft.intake.notes} onChange={(event) => updateIntake({ notes: event.target.value })} rows={3} placeholder="记录用户锁定项或需要保留的商品细节" /></label>
        <button type="button" className="primary-button director-action" onClick={() => void requestAnalysis()} disabled={!ready || busyAction !== null || workflow !== null}>
          <WandSparkles size={16} />{busyAction === 'analyze' ? '正在创建并分析' : workflow ? '已创建任务' : '创建任务并分析'}
        </button>
      </section>

      <section className="director-panel director-panel--directions" aria-labelledby="director-directions-title">
        <div className="director-panel__heading">
          <div><span className="director-panel__index">02</span><div><h2 id="director-directions-title">Direction Candidates</h2><p>候选只表达创意差异，不代表已经分析或获得生成授权。</p></div></div>
          <span className="director-state">{workflow?.snapshot.plan ? `${draft.directions.length} 个候选` : '等待分析'}</span>
        </div>
        <div className="director-direction-list">
          {draft.directions.map((direction) => <button
            key={direction.id}
            type="button"
            className={`director-direction${draft.selectedDirectionId === direction.id ? ' is-selected' : ''}`}
            onClick={() => void chooseDirection(direction)}
            disabled={!workflow || workflow.status !== 'AWAITING_DIRECTION' || busyAction !== null}
          >
            <span className="director-direction__marker">{direction.id}</span>
            <span className="director-direction__body"><strong>{direction.title}</strong><small>{direction.summary}</small><span className="director-direction__facts"><em>{direction.human}</em><em>{direction.scene}</em><em>{direction.camera}</em></span></span>
            <span className="director-direction__check">{draft.selectedDirectionId === direction.id ? <Check size={17} /> : '选择'}</span>
          </button>)}
        </div>
        <div className="director-summary">
          <div><span>DNA / Reality Summary</span><strong>{selectedDirection ? selectedDirection.title : '等待方向选择'}</strong></div>
          <p>{selectedDirection ? selectedDirection.summary : '上传正面图并完成分析后，服务端会返回 A、B、C 三个离线方向候选。'}</p>
          {snapshot?.referenceStrength !== undefined ? <small>已有参考强度：{snapshot.referenceStrength}</small> : <small>尚未关联 Reality、Spatial 或 Video DNA</small>}
        </div>
      </section>

      <section className="director-panel director-panel--package" aria-labelledby="director-package-title">
        <div className="director-panel__heading"><div><span className="director-panel__index">03</span><div><h2 id="director-package-title">Production Package</h2><p>生产包由后端版本化合同提供，前端不复制 Prompt 真源。</p></div></div></div>
        <div className="director-package-state"><LockKeyhole size={18} /><div><strong>{packageState}</strong><span>此闭环只调用离线 Fake 接口。候选沿用商品正面图作为占位，不能作为真实首帧、审核合格或交付素材。</span></div></div>
        <dl className="director-package-list">
          <div><dt>商品事实</dt><dd>{ready ? '正面已提供' : '未提供'}</dd></div>
          <div><dt>方向选择</dt><dd>{selectedDirection ? selectedDirection.id : '未选择'}</dd></div>
          <div><dt>任务状态</dt><dd>{workflow?.status ?? '未创建'}</dd></div>
        </dl>
        {workflow?.snapshot.package && !firstFrameCandidates.length ? <div className="director-package-actions">
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
          <button type="button" className="secondary-button" onClick={() => void refreshWorkflow()} disabled={busyAction !== null}>
            <RefreshCw size={16} />{busyAction === 'refresh' ? '正在刷新' : '刷新任务状态'}
          </button>
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
              <img src={draft.intake.productFrontPreviewUrl} alt="离线 Fake 首帧占位，沿用商品正面图" style={{ width: '100%', maxHeight: 280, objectFit: 'contain' }} />
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
            </section>
          })}
        </section> : null}
        <section className="director-storyboard" aria-labelledby="director-storyboard-title">
          <div className="director-panel__heading">
            <div>
              <span className="director-panel__index">04</span>
              <div>
                <h2 id="director-storyboard-title">Storyboard / SHOT_01</h2>
                <p>首帧选择后，单独授权并验证第一镜头的离线分镜候选。</p>
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
              <span>分镜包继承已选离线首帧的服务端合同。Fake 分镜仅用于验证 workflow，不具备真实视频生产或交付资格。</span>
            </div>
          </div>
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
                <img src={draft.intake.productFrontPreviewUrl} alt="离线 Fake 分镜占位，沿用商品正面图" style={{ width: '100%', maxHeight: 280, objectFit: 'contain' }} />
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
                <p>整理未来生产桥接所需的服务端校验边界，当前不提交 Provider。</p>
              </div>
            </div>
            <span className="director-state">{bridgePreparation?.status ?? '等待 handoff'}</span>
          </div>
          {bridgePreparation ? <div className="director-package-state">
            <LockKeyhole size={18} />
            <div>
              <strong>只读桥接上下文 · Provider submission disabled</strong>
              <span>package、授权、来源哈希、许可、预算和 execution state 必须在服务端提交前重新验证。</span>
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
        </section>
      </section>
    </div>
    {notice ? <div className="director-notice" role="status">{notice}</div> : null}
  </section>
}
