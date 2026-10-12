import { LockKeyhole } from 'lucide-react'
import type { CreativeBrief } from './contracts'
import type { DirectorTaskResponse } from './directorApi'
import type { DirectorDraft } from './directorModel'
import type { ProductionBridgePreparation } from './productionBridge'
import {
  selectDirectorBriefSummary,
  selectDirectorBridgeExplanation,
  selectDirectorDirectionComparison,
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

export function DirectorDirectionComparison({ workflow, draft }: { workflow: DirectorTaskResponse | null; draft: DirectorDraft }) {
  const candidates = selectDirectorDirectionComparison(workflow, draft)
  if (!candidates.length) return <p className="director-empty">尚无服务端方向候选</p>
  return <section className="director-comparison" aria-label="方向差异对比">
    <h3>场景 / 行为对比</h3>
    <div className="director-comparison__grid">
      {candidates.map((candidate) => <article key={candidate.id} className={`director-comparison__item${candidate.selected ? ' is-selected' : ''}`}>
        <h4>方向 {candidate.id}{candidate.selected ? <span>已选择</span> : null}</h4>
        <dl className="director-evidence-list">
          <div><dt>场景 · 服务端分析</dt><dd>{candidate.scene || '未提供'}</dd></div>
          <div><dt>行为 · 服务端分析</dt><dd>{candidate.behavior || '未提供'}</dd></div>
        </dl>
        {candidate.planningReference ? <details className="director-reference">
          <summary>本地规划参考 · 非分析证据</summary>
          <dl className="director-evidence-list">
            <div><dt>人物</dt><dd>{candidate.planningReference.human}</dd></div>
            <div><dt>镜头</dt><dd>{candidate.planningReference.camera}</dd></div>
            <div><dt>情绪</dt><dd>{candidate.planningReference.emotion}</dd></div>
          </dl>
        </details> : null}
      </article>)}
    </div>
  </section>
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
