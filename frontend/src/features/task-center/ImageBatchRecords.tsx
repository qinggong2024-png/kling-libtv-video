import { useState } from 'react'
import { CheckCircle2, Images } from 'lucide-react'
import type { ImageGenerationBatch, ImageGenerationBatchOutput } from '../../types'
import { FoundationDrawer } from '../../shared/components/ui'
import { SectionHeading } from '../../shared/components/Section'
import { ImageOutputReview } from '../image-studio/ImageResultTools'
import { AuthenticatedAssetPreview } from '../image-studio/shared/ImageAssets'

export function ImageBatchRecords({ batches, query, onChanged }: { batches: ImageGenerationBatch[]; query: string; onChanged: () => void }) {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [review, setReview] = useState<ImageGenerationBatchOutput | null>(null)
  const keyword = query.trim().toLowerCase()
  const visible = batches.filter((batch) => !keyword || [batch.name, batch.id, ...batch.items.flatMap((item) => [item.outfitName, item.clientTaskId, ...(item.prompts ?? [])])].join(' ').toLowerCase().includes(keyword))
  const selected = batches.find((batch) => batch.id === selectedId)
  return <section aria-label="图片批次任务" className="records-completed">
    <SectionHeading title="图片批次" count={visible.length} />
    <div className="task-table">{visible.map((batch) => <button type="button" className="task-table-row" key={batch.id} onClick={() => setSelectedId(batch.id)}>
      <span className="task-name-cell"><Images size={20} /><span><strong>{batch.name ?? batch.id}</strong><small>图片 · {batch.id}</small></span></span>
      <span>{batch.status}</span><span>{batch.items.reduce((count, item) => count + item.outputs.length, 0)} 个结果</span><span>{batch.createdAt?.slice(0, 10)}</span><span />
    </button>)}</div>
    {selected ? <FoundationDrawer open title={selected.name ?? '图片批次详情'} eyebrow="服务端档案" onClose={() => setSelectedId(null)}>
      <p>批次 {selected.id} · {selected.status}</p>
      {selected.items.map((item) => <section key={item.id}>
        <h3>{item.outfitName ?? item.outfitId}</h3><p>{item.status} · {item.clientTaskId} · {item.modelId}</p>
        {item.error ? <p role="alert">{item.error.code} · {item.error.message}</p> : null}
        <details><summary>Prompt 快照</summary>{(item.prompts ?? []).map((prompt, index) => <pre key={index} style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{prompt}</pre>)}</details>
        <div className="results-grid">{item.outputs.map((output) => <article key={output.id} className="image-output-card">
          <AuthenticatedAssetPreview file={null} url={output.downloadUrl ?? output.url} alt={output.label} />
          <strong>{output.label}</strong><p>{output.synthetic ? 'Offline Fake · 不可交付' : output.qualificationStatus === 'QUALIFIED' ? '已审核合格' : output.qualificationStatus === 'REJECTED' ? '已拒绝' : '待人工审核'}</p>
          <button type="button" className="secondary-button" disabled={output.synthetic} onClick={() => setReview(output)}><CheckCircle2 size={16} />审核图片</button>
        </article>)}</div>
      </section>)}
    </FoundationDrawer> : null}
    {review ? <ImageOutputReview output={{ ...review, file: null }} onClose={() => setReview(null)} onSaved={() => { setReview(null); onChanged() }} /> : null}
  </section>
}
