import { useState, type ReactNode } from 'react'
import { Copy, Download } from 'lucide-react'
import type { DirectorTaskResponse } from './directorApi'
import {
  copyCreativePackage,
  creativePackageDisplayText,
  creativePackageFieldSource,
  creativePackageFieldStatus,
  creativePackageText,
  downloadCreativePackage,
  packageFields,
  isRecord,
  selectCreativePackageExport,
} from './creativePackageExport'
import type { DirectorSpatialPlan } from './spatialPlanning'
import './creativePackageExport.css'

export function CreativePackageExportView({ workflow, packageId, spatialPlan, children }: {
  workflow: DirectorTaskResponse | null
  packageId: string
  spatialPlan?: DirectorSpatialPlan | null
  children?: ReactNode
}) {
  const document = selectCreativePackageExport(workflow, packageId)
  if (!document) return <>
    <p className="director-empty">Creative Package · 暂无可导出合同，未提供交接内容。</p>
    {children ? <details className="creative-package-technical"><summary>技术详情</summary>{children}</details> : null}
  </>
  return <PackageExportContent key={packageId} document={document} packageId={packageId} spatialPlan={spatialPlan}>{children}</PackageExportContent>
}

function PackageExportContent({ document, packageId, spatialPlan, children }: {
  document: NonNullable<ReturnType<typeof selectCreativePackageExport>>
  packageId: string
  spatialPlan?: DirectorSpatialPlan | null
  children?: ReactNode
}) {
  const [notice, setNotice] = useState('')
  const [copying, setCopying] = useState(false)
  const provenance = isRecord(document.provenance) ? document.provenance : {}
  const shots = Array.isArray(document.shotPlan) ? document.shotPlan : []
  const checklist = Array.isArray(document.qualityChecklist) ? document.qualityChecklist : []
  const requirements = packageFields.filter(([field]) => ['audience', 'characterDNA', 'sceneDNA', 'cameraDNA'].includes(field))
  async function copy(text: string) {
    setCopying(true)
    setNotice('')
    try {
      await copyCreativePackage(text)
      setNotice('已复制')
    } catch {
      setNotice('复制失败，可下载 JSON 或选择文本。')
    } finally {
      setCopying(false)
    }
  }
  function download() {
    try {
      downloadCreativePackage(document, packageId)
      setNotice('已导出 JSON')
    } catch {
      setNotice('导出失败，请重试。')
    }
  }
  return <section className="creative-package-export" aria-label="创意交接文档">
    <p className="creative-package-export__scope">{provenance.synthetic === true ? 'Fake · 离线合成 · 不可交付' : '仅规划 · 待人工验证 · 不可交付'}。规划内容不等于已验证生产内容。</p>
    <div className="creative-package-export__tools" role="group" aria-label="Creative Package 导出">
      <button type="button" title="复制完整 Creative Package" aria-label="复制完整 Creative Package" disabled={copying} onClick={() => void copy(creativePackageText(document))}><Copy size={16} /></button>
      <button type="button" title="下载 Creative Package JSON" aria-label="下载 Creative Package JSON" onClick={download}><Download size={16} /></button>
      <span role="status" aria-live="polite">{notice}</span>
    </div>
    <section className="creative-package-section creative-package-section--primary" aria-label="制作要求">
      <h3>制作要求</h3>
      <dl className="creative-package-export__fields">
        <div><dt>商品约束</dt><dd>未提供独立约束摘要；保留要求以冻结图片提示词原文为准。</dd></div>
        {requirements.map(([field, label]) => <div key={field}>
          <dt>{label}</dt>
          <dd><span className="creative-package-meta">{creativePackageFieldStatus(document, field)} · 来源：{creativePackageFieldSource(document, field)}</span><p>{creativePackageDisplayText(field, document[field])}</p></dd>
        </div>)}
      </dl>
    </section>
    {(['imagePrompt', 'videoPrompt'] as const).map((field) => {
      const label = field === 'imagePrompt' ? '图片生成提示词' : '视频创作提案'
      const value = document[field]
      return <section key={field} className="creative-package-section creative-package-prompt" aria-label={label}>
        <div className="creative-package-section__heading">
          <h3>{label}</h3>
          {typeof value === 'string' && value !== '' ? <button type="button" title={`复制${label}全文`} aria-label={`复制${label}全文`} disabled={copying} onClick={() => void copy(value)}><Copy size={16} /></button> : null}
        </div>
        <p className="creative-package-meta">用途：{field === 'imagePrompt' ? `${provenance.shotId === 'FIRST_FRAME' ? '首帧' : provenance.shotId || '未提供镜头'}图片创作参考` : '视频制作的人工确认与交接参考'}</p>
        <p className="creative-package-meta">来源：{creativePackageFieldSource(document, field)} · {creativePackageFieldStatus(document, field)}</p>
        <pre className="creative-package-prompt__preview" tabIndex={0} aria-label={`${label}原文`}>{creativePackageDisplayText(field, value)}</pre>
      </section>
    })}
    <section className="creative-package-section" aria-label="镜头规划">
      <h3>镜头规划</h3>
      {spatialPlan ? <>
        <p className="creative-package-meta">本地创意提案 · 未验证。此规划未写入冻结交接合同，不代表完整视频时间线。</p>
        <ol className="creative-package-shots">
          {spatialPlan.actorBlocking.map((shot) => <li key={shot.shotId}>
            <strong>{shot.shotId}</strong>
            <p>{shot.start.worldZone} → {shot.end.worldZone}</p>
            <p>{shot.movementPath.join(' → ')}</p>
            <small>{shot.contactTransition || '接触关系未提供'}</small>
          </li>)}
        </ol>
      </> : null}
      <h4>已有镜头包记录</h4>
      <p className="creative-package-meta">当前包及冻结父包的关联记录，不代表已完成分镜；完整标识保留在技术详情。</p>
      {shots.length ? <ol className="creative-package-shots">
        {shots.map((shot, index) => {
          const item = isRecord(shot) ? shot : {}
          const source = isRecord(item.sourcePackage) ? item.sourcePackage : {}
          return <li key={index}><strong>{typeof item.shotId === 'string' ? item.shotId : '未提供镜头'}</strong>
            <span>版本 {typeof item.revision === 'number' ? `r${item.revision}` : '未提供'} · 未验证生产内容</span>
            <p>{source.purpose === 'FIRST_FRAME' || item.shotId === 'FIRST_FRAME' ? '首帧图片规划' : source.purpose === 'VIDEO_STORYBOARD' ? '镜头图片规划' : '用途未提供'}</p>
          </li>
        })}
      </ol> : <p>未提供 · 待人工确认</p>}
    </section>
    <section className="creative-package-section" aria-label="质量检查">
      <h3>质量检查</h3>
      <p className="creative-package-meta">待人工检查；以下规则记录不代表质检通过。</p>
      {checklist.length ? <ul className="creative-package-checklist">
        {checklist.map((entry, index) => {
          const item = isRecord(entry) ? entry : {}
          return <li key={index}><strong>{typeof item.dimension === 'string' ? item.dimension : '检查项'}</strong>
            <p>{typeof item.expectation === 'string' ? item.expectation : '未提供'}</p>
            {typeof item.judgment_standard === 'string' ? <details><summary>判断标准</summary><p>{item.judgment_standard}</p></details> : null}
          </li>
        })}
      </ul> : <p>未提供 · 待人工确认</p>}
    </section>
    <details className="creative-package-technical">
      <summary>技术详情</summary>
      <div className="creative-package-technical__body">
        {children}
        <h3>来源与合同</h3>
        <pre>{JSON.stringify(Object.fromEntries(Object.entries(document).filter(([key]) => !packageFields.some(([field]) => field === key))), null, 2)}</pre>
        <h4>冻结镜头包关联</h4>
        <pre>{JSON.stringify(document.shotPlan, null, 2)}</pre>
      </div>
    </details>
  </section>
}
