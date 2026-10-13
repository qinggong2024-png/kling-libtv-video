import { useState } from 'react'
import { Copy, Download } from 'lucide-react'
import type { DirectorTaskResponse } from './directorApi'
import {
  copyCreativePackage,
  creativePackageDisplayText,
  creativePackageText,
  downloadCreativePackage,
  packageFields,
  selectCreativePackageExport,
} from './creativePackageExport'
import './creativePackageExport.css'

export function CreativePackageExportView({ workflow, packageId }: { workflow: DirectorTaskResponse | null; packageId: string }) {
  const document = selectCreativePackageExport(workflow, packageId)
  if (!document) return <p className="director-empty">Creative Package · 暂无可导出合同</p>
  return <PackageExportContent key={`${packageId}:${workflow?.state_version}`} document={document} packageId={packageId} />
}

function PackageExportContent({ document, packageId }: { document: NonNullable<ReturnType<typeof selectCreativePackageExport>>; packageId: string }) {
  const [notice, setNotice] = useState('')
  const [copying, setCopying] = useState(false)
  const statuses = document.fieldStatus && typeof document.fieldStatus === 'object' ? document.fieldStatus as Record<string, unknown> : {}
  const provenance = document.provenance && typeof document.provenance === 'object' ? document.provenance as Record<string, unknown> : {}
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
  return <details className="creative-package-export" open>
    <summary>Creative Package · 人工生产交接</summary>
    <p className="creative-package-export__scope">{provenance.synthetic === true ? '离线合成 · 不可交付' : '待人工验证 · 不可交付'}</p>
    <div className="creative-package-export__tools" role="group" aria-label="Creative Package 导出">
      <button type="button" title="复制完整 Creative Package" aria-label="复制完整 Creative Package" disabled={copying} onClick={() => void copy(creativePackageText(document))}><Copy size={16} /></button>
      <button type="button" title="下载 Creative Package JSON" aria-label="下载 Creative Package JSON" onClick={download}><Download size={16} /></button>
      <span role="status" aria-live="polite">{notice}</span>
    </div>
    <dl className="creative-package-export__fields">
      {packageFields.map(([field, label]) => <div key={field}>
        <dt>{label}<small>{statuses[field] === 'PROPOSED' ? '模板建议' : statuses[field] === 'UNRESOLVED' ? '待补充' : '已记录'}</small>{(field === 'imagePrompt' || field === 'videoPrompt') && typeof document[field] === 'string' && document[field] !== '' ? <button type="button" title={`复制${label}`} aria-label={`复制${label}`} disabled={copying} onClick={() => void copy(document[field] as string)}><Copy size={14} /></button> : null}</dt>
        <dd><pre>{creativePackageDisplayText(field, document[field])}</pre></dd>
      </div>)}
    </dl>
    <details>
      <summary>来源与合同</summary>
      <pre>{JSON.stringify(Object.fromEntries(Object.entries(document).filter(([key]) => !packageFields.some(([field]) => field === key))), null, 2)}</pre>
    </details>
  </details>
}
