import { Film, Image as ImageIcon, Library } from 'lucide-react'
import type { ImageGenerationBatch, Task, Variant } from '../../types'
import { DataFreshness } from '../../shared/components/DataFreshness'
import { EmptyState, SectionHeading } from '../../shared/components/Section'
import { ResultCard } from '../production/ResultCard'
import { AuthenticatedAssetPreview } from '../image-studio/shared/ImageAssets'
import { useState } from 'react'
import { AssetPreviewDialog } from '../image-studio/ImageResultTools'

export function GeneratedAssetsView({
  tasks,
  imageBatches = [],
  lastSyncedAt,
  syncError = false,
  onOpen,
  onPlay,
  onRemix,
  onFeedbackChanged,
  onCreateTask,
  canReview = false,
  cutflowEnabled = false,
  cutflowCanWrite = true,
}: {
  tasks: Task[]
  imageBatches?: ImageGenerationBatch[]
  lastSyncedAt: number | null
  syncError?: boolean
  onOpen: (task: Task) => void
  onPlay: (task: Task, variant: Variant) => void
  onRemix: (task: Task) => void
  onFeedbackChanged: (task: Task) => void
  onCreateTask: () => void
  canReview?: boolean
  cutflowEnabled?: boolean
  cutflowCanWrite?: boolean
}) {
  const [query, setQuery] = useState('')
  const [mediaType, setMediaType] = useState<'all' | 'image' | 'video'>('all')
  const [preview, setPreview] = useState<{ url: string; label: string } | null>(null)
  const keyword = query.trim().toLowerCase()
  const results = tasks
    .flatMap((task) => task.variants.map((variant) => ({ task, variant })))
    .filter(({ variant }) => Boolean(variant.downloadArtifactId) && variant.finalApprovalStatus === 'APPROVED')
    .filter(({ task, variant }) => mediaType !== 'image' && (!keyword || [task.title, task.id, variant.id, variant.promptText].join(' ').toLowerCase().includes(keyword)))
    .sort((left, right) => Date.parse(right.task.updatedAt) - Date.parse(left.task.updatedAt))
  const imageResults = imageBatches.flatMap((batch) => batch.items.flatMap((item) => item.outputs
    .filter((output) => !output.synthetic && output.qualificationStatus === 'QUALIFIED' && output.artifactId && output.downloadUrl)
    .filter((output) => mediaType !== 'video' && (!keyword || [batch.name, batch.id, item.outfitName, output.label, output.id].join(' ').toLowerCase().includes(keyword)))
    .map((output) => ({ batch, item, output }))))

  return <div className="page-view generated-assets-view">
    <div className="page-title generated-assets-title">
      <div>
        <span>结果工作台</span>
        <h1>生成资产</h1>
        <p>集中查看生成结果、下载和审核状态；结果始终关联到原任务，不复制任务记录。</p>
      </div>
      <DataFreshness timestamp={lastSyncedAt} stale={syncError} />
    </div>
    <section className="generated-assets-summary" aria-label="生成资产说明">
      <Library size={20} />
      <div><strong>{results.length + imageResults.length} 个可查看结果</strong><span>仅展示逐结果审核通过的媒体；任务中心保留来源、Prompt、过程、审核和版本链路。</span></div>
    </section>
    <section className="generated-assets-results" aria-label="已生成结果">
      <div className="records-page-actions"><label className="search-field"><input aria-label="搜索生成资产" placeholder="搜索生成资产" value={query} onChange={(event) => setQuery(event.target.value)} /></label><label>媒体类型<select value={mediaType} onChange={(event) => setMediaType(event.target.value as typeof mediaType)}><option value="all">全部</option><option value="image">图片</option><option value="video">视频</option></select></label></div>
      <SectionHeading title="已生成结果" count={results.length + imageResults.length} />
      {results.length || imageResults.length ? <div className="results-grid results-grid--library">
        {imageResults.map(({ batch, item, output }) => <article className="result-card image-result-card" key={output.id}>
          <button type="button" className="result-card-media" aria-label={`预览${output.label}`} onClick={() => setPreview({ url: output.downloadUrl ?? output.url, label: output.label })}><AuthenticatedAssetPreview file={null} url={output.downloadUrl ?? output.url} alt={output.label} /></button>
          <div className="result-card-body"><div className="result-card-title"><strong>{batch.name ?? '图片批次'} · {item.outfitId}</strong><span className="result-card-badge"><ImageIcon size={13} /> 图片</span></div><p>已审核通过，可作为图片、首帧或分镜输入</p><small>来源批次 {batch.id} · 输出 {output.id}</small></div>
        </article>)}
        {results.map(({ task, variant }) => <ResultCard
        key={variant.id}
        task={task}
        variant={variant}
        onPlay={() => onPlay(task, variant)}
        onRemix={() => onRemix(task)}
        onOpen={() => onOpen(task)}
        onFeedbackChanged={onFeedbackChanged}
        canReview={canReview}
        cutflowEnabled={cutflowEnabled}
        cutflowCanWrite={cutflowCanWrite}
      />)}</div> : <EmptyState
        icon={<Film size={24} />}
        title="还没有可查看的生成资产"
        description="完成图片或视频任务后，结果会自动出现在这里；任务中心仍保存完整生产档案。"
        action={<button type="button" className="primary-button" onClick={onCreateTask}>去视频工作室</button>}
      />}
    </section>
    {preview ? <AssetPreviewDialog file={null} url={preview.url} label={preview.label} onClose={() => setPreview(null)} /> : null}
  </div>
}
