import { Check, LockKeyhole } from 'lucide-react'
import { CreativePackageExportView } from './CreativePackageExportView'
import type { CreativeBrief } from './contracts'
import type { DirectorTaskResponse } from './directorApi'
import type { DirectorDirection } from './directorModel'
import type { ProductionBridgePreparation } from './productionBridge'
import {
  selectDirectorBriefSummary,
  selectDirectorBridgeExplanation,
  selectDirectorPackageEvidence,
} from './directorPresentation'

export function DirectorBriefSummary({ brief }: { brief: CreativeBrief }) {
  return <details className="director-evidence director-brief-summary">
    <summary>Brief 摘要 · 项目规划记录</summary>
    <dl className="director-evidence-list">
      {selectDirectorBriefSummary(brief).map((item) => <div key={item.label}><dt>{item.label}</dt><dd>{item.value}</dd></div>)}
    </dl>
    <p className="director-evidence__note">未纳入当前离线分析请求或服务端生产包。</p>
  </details>
}

export function DirectorDirectionCard({ direction, workflow, selected, confirmed, disabled, onSelect }: {
  direction: DirectorDirection
  workflow: DirectorTaskResponse | null
  selected: boolean
  confirmed: boolean
  disabled: boolean
  onSelect: () => void
}) {
  const result = workflow?.snapshot.plan?.directions.find((candidate) => candidate.id === direction.id)
  const resultSource = workflow?.mode === 'OFFLINE_FAKE_ONLY' ? 'AI Result · 离线 Fake' : 'AI Result'
  return <article
    className={`director-direction${selected ? ' is-selected' : ''}${confirmed ? ' is-confirmed' : ''}`}
    aria-label={`方向 ${direction.id} · ${direction.title}`}
    onClick={(event) => {
      if (disabled || (event.target as HTMLElement).closest('button, details')) return
      onSelect()
    }}
  >
    <button type="button" className="director-direction__select" aria-pressed={selected} disabled={disabled} onClick={onSelect}>
      <span className="director-direction__topline">
        <span className="director-direction__marker">{direction.id}</span>
        <span className="director-direction__heading"><strong>{direction.title || '未提供'}</strong><small>名称 · 创意提案</small></span>
      </span>
      <span className="director-direction__section">
        <span className="director-direction__label">Creative Summary <em>{result ? '结果整理' : 'Unknown'}</em></span>
        <span className="director-direction__value">{result ? direction.summary || '未提供' : '未提供'}</span>
      </span>
      <span className="director-direction__check">{confirmed ? <><Check size={16} />已确认</> : selected ? <><Check size={16} />已选择</> : '选择'}</span>
    </button>
    <div className="director-direction__section">
      <span className="director-direction__label">Execution Concept <em>{result ? resultSource : 'Unknown'}</em></span>
      <dl className="director-direction__facts">
        <div><dt>Scene · 场景</dt><dd>{result?.scene || '未提供'}</dd></div>
        <div><dt>Behavior · 行为</dt><dd>{result?.behavior || '未提供'}</dd></div>
      </dl>
    </div>
    <div className="director-direction__section">
      <span className="director-direction__label">Visual Proposal <em>创意提案</em></span>
      <dl className="director-direction__facts">
        <div><dt>Camera · 镜头</dt><dd>{direction.camera || '未提供'}</dd></div>
        <div><dt>Emotion · 情绪</dt><dd>{direction.emotion || '未提供'}</dd></div>
      </dl>
    </div>
    <details className="director-direction__sources">
      <summary>Information Source · 信息来源</summary>
      <dl className="director-direction__source-list">
        <div><dt>{result ? resultSource : 'Unknown'}</dt><dd>{result ? '场景 / 行为：服务端结果。摘要：前端按结果整理。' : '尚无服务端方向结果。'}</dd></div>
        <div><dt>Creative Proposal · 创意提案</dt><dd>名称 / 镜头 / 情绪：本地规划参考，非 AI 分析结果。</dd></div>
        <div><dt>User Input · 用户输入</dt><dd>商品图 / 品牌归属；不代表方向已验证商品证据。</dd></div>
        <div><dt>Unknown · 未提供</dt><dd>目标受众适配 / Product Evidence / Trade-off。</dd></div>
      </dl>
    </details>
  </article>
}

export function DirectorPackageEvidence({ workflow, shotId }: { workflow: DirectorTaskResponse | null; shotId: 'FIRST_FRAME' | 'SHOT_01' }) {
  const evidence = selectDirectorPackageEvidence(workflow, shotId)
  if (!evidence) return <p className="director-empty">{shotId} · 暂无服务端生产包</p>
  const fields = [
    ['Package ID', evidence.package_id],
    ['版本', evidence.revision === undefined ? undefined : `r${evidence.revision}`],
    ['镜头', evidence.shot_id],
    ['父包', evidence.parent_package_id ?? '无父包'],
    ['商品事实版本', evidence.facts_revision],
    ['Ruleset', evidence.ruleset],
    ['Locks hash', evidence.locks_hash],
    ['Preservation hash', evidence.preservation_hash],
  ]
  return <section className="director-package-evidence" aria-label={`${shotId} 生产包证据`}>
    <div className="director-package-evidence__heading"><LockKeyhole size={16} /><h3>{shotId} · 服务端生产包</h3></div>
    <dl className="director-evidence-list director-evidence-list--package">
      {fields.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value === undefined || value === '' ? '未提供' : value}</dd></div>)}
    </dl>
    <details className="director-evidence">
      <summary>Prompt · 服务端只读</summary>
      <pre className="director-prompt">{evidence.prompt || '未提供'}</pre>
    </details>
    <details className="director-evidence">
      <summary>Reality 决策 · {evidence.reality?.length ?? 0} 项</summary>
      {evidence.reality?.length ? <dl className="director-reality">
        {evidence.reality.map((item, index) => <div key={`${item.dimension}-${index}`}><dt>{item.dimension}</dt><dd><strong>{item.decision}</strong><p>{item.evidence || '未提供证据'}</p></dd></div>)}
      </dl> : <p className="director-empty">尚无服务端 Reality 决策</p>}
    </details>
    {evidence.package_id ? <CreativePackageExportView workflow={workflow} packageId={evidence.package_id} /> : null}
  </section>
}

export function DirectorBridgeStatus({ preparation, workflow }: { preparation: ProductionBridgePreparation | null; workflow: DirectorTaskResponse | null }) {
  const explanation = selectDirectorBridgeExplanation(preparation, workflow)
  if (!preparation || !explanation) return <p className="director-empty">暂无 handoff · 未执行生产预检</p>
  return <div className="director-bridge-explanation">
    <ol className="director-qualification-path" aria-label="创意与生产资格">
      <li><strong>创意决策</strong><span>方向 {preparation.directionId} · {preparation.shotId}</span></li>
      <li><strong>生产资格</strong><span>{preparation.status} · 尚未完成服务端预检</span></li>
      <li><strong>生产提交</strong><span>禁止 Provider submission</span></li>
    </ol>
    <p className="director-evidence__note">待验证不等于验证失败。OFFLINE_SYNTHETIC_ONLY 不可交付。</p>
    {explanation.executionWarning ? <p className="director-execution-warning" role="status">{explanation.executionWarning}</p> : null}
    <h3>当前阻断原因</h3>
    <ul className="director-blocking-reasons">
      {explanation.blockingReasons.map((reason) => <li key={reason.code}>{reason.message}</li>)}
    </ul>
    <details className="director-evidence">
      <summary>服务端预检要求 · {explanation.checks.length} 项</summary>
      <dl className="director-preflight-checks">
        {explanation.checks.map((check) => <div key={check.key}><dt>{check.label}<span>{check.status}</span></dt><dd>{check.requirement}</dd></div>)}
      </dl>
    </details>
    <h3>下一检查点</h3>
    <ol className="director-next-steps">
      {explanation.nextSteps.map((step) => <li key={step.code}>{step.label}</li>)}
    </ol>
  </div>
}
