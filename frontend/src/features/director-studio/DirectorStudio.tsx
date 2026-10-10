import { Check, FileImage, LockKeyhole, Sparkles, WandSparkles } from 'lucide-react'
import { useMemo, useState, type ChangeEvent } from 'react'
import { useOptionalCreativeProject } from '../../creative-project/hooks'
import type { CreativeIntelligenceSnapshot } from '../../creative-project/types'
import {
  createDirectorDraft,
  isDirectorIntakeReady,
  selectDirectorDirection,
  type DirectorDraft,
  type DirectorDirection,
  type DirectorProductIntake,
} from './directorModel'
import './directorStudio.css'

function updateProjectSnapshot(
  snapshot: CreativeIntelligenceSnapshot | undefined,
): CreativeIntelligenceSnapshot | undefined {
  return snapshot
}

export function DirectorStudio() {
  const projectContext = useOptionalCreativeProject()
  const [draft, setDraft] = useState<DirectorDraft>(createDirectorDraft)
  const [notice, setNotice] = useState('')
  const ready = isDirectorIntakeReady(draft.intake)
  const selectedDirection = draft.directions.find((direction) => direction.id === draft.selectedDirectionId) ?? null
  const packageState = selectedDirection ? '已选择方向，等待生产包合同接入' : '选择方向后生成生产包预览'
  const snapshot = useMemo(
    () => updateProjectSnapshot(projectContext?.project.intelligenceSnapshot),
    [projectContext?.project.intelligenceSnapshot],
  )

  const updateIntake = (patch: Partial<DirectorProductIntake>) => {
    setDraft((current) => ({ ...current, intake: { ...current.intake, ...patch } }))
    setNotice('')
  }

  const onFrontImage = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    const previewUrl = URL.createObjectURL(file)
    updateIntake({ productFrontName: file.name, productFrontPreviewUrl: previewUrl })
  }

  const chooseDirection = (direction: DirectorDirection) => {
    const next = selectDirectorDirection(draft, direction.id)
    setDraft(next)
    projectContext?.updateProject({
      currentStage: 'AWAITING_DIRECTION',
      metadata: {
        directorDirectionId: direction.id,
        directorBrandMode: next.intake.brandMode,
      },
    })
    setNotice('方向已记录。选择方向不会授权图片或视频生成。')
  }

  const requestAnalysis = () => {
    setNotice(ready
      ? '分析接口尚未接入。本阶段只保存输入，不会调用 Provider 或创建任务。'
      : '请先上传商品正面图。')
  }

  return <section className="director-studio page-view" aria-label="智能导演">
    <header className="director-studio__header">
      <div>
        <span className="director-studio__eyebrow"><Sparkles size={14} />Image Studio / Director</span>
        <h1>智能导演</h1>
        <p>从真实商品输入开始，整理方向、锁定判断，再交给现有生产流程执行。</p>
      </div>
      <span className="director-studio__contract"><LockKeyhole size={14} />当前为规划模式</span>
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
          <input type="file" accept="image/*" onChange={onFrontImage} />
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
        <label className="director-field"><span>创作备注 <small>可选</small></span><textarea value={draft.intake.notes} onChange={(event) => updateIntake({ notes: event.target.value })} rows={3} placeholder="记录用户锁定项或需要保留的商品细节" /></label>
        <button type="button" className="primary-button director-action" onClick={requestAnalysis}><WandSparkles size={16} />整理方向候选</button>
      </section>

      <section className="director-panel director-panel--directions" aria-labelledby="director-directions-title">
        <div className="director-panel__heading">
          <div><span className="director-panel__index">02</span><div><h2 id="director-directions-title">Direction Candidates</h2><p>候选只表达创意差异，不代表已经分析或获得生成授权。</p></div></div>
          <span className="director-state">{draft.directions.length} 个候选</span>
        </div>
        <div className="director-direction-list">
          {draft.directions.map((direction) => <button
            key={direction.id}
            type="button"
            className={`director-direction${draft.selectedDirectionId === direction.id ? ' is-selected' : ''}`}
            onClick={() => chooseDirection(direction)}
          >
            <span className="director-direction__marker">{direction.id}</span>
            <span className="director-direction__body"><strong>{direction.title}</strong><small>{direction.summary}</small><span className="director-direction__facts"><em>{direction.human}</em><em>{direction.scene}</em><em>{direction.camera}</em></span></span>
            <span className="director-direction__check">{draft.selectedDirectionId === direction.id ? <Check size={17} /> : '选择'}</span>
          </button>)}
        </div>
        <div className="director-summary">
          <div><span>DNA / Reality Summary</span><strong>{selectedDirection ? selectedDirection.title : '等待方向选择'}</strong></div>
          <p>{selectedDirection ? selectedDirection.summary : '真实观察、用户锁定和创意假设将在后端合同接入后分别显示。'}</p>
          {snapshot?.referenceStrength !== undefined ? <small>已有参考强度：{snapshot.referenceStrength}</small> : <small>尚未关联 Reality、Spatial 或 Video DNA</small>}
        </div>
      </section>

      <section className="director-panel director-panel--package" aria-labelledby="director-package-title">
        <div className="director-panel__heading"><div><span className="director-panel__index">03</span><div><h2 id="director-package-title">Production Package</h2><p>生产包由后端版本化合同提供，前端不复制 Prompt 真源。</p></div></div></div>
        <div className="director-package-state"><LockKeyhole size={18} /><div><strong>{packageState}</strong><span>分析、首帧、分镜和视频授权在接入真实合同前保持关闭。</span></div></div>
        <dl className="director-package-list"><div><dt>商品事实</dt><dd>{ready ? '正面已提供' : '未提供'}</dd></div><div><dt>方向选择</dt><dd>{selectedDirection ? selectedDirection.id : '未选择'}</dd></div><div><dt>生成任务</dt><dd>未创建</dd></div></dl>
      </section>
    </div>
    {notice ? <div className="director-notice" role="status">{notice}</div> : null}
  </section>
}
