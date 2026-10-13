import { AlertTriangle, ArrowLeft, CheckCircle2, ChevronRight, Clock3, Columns2, History, Images, LoaderCircle, Package, Plus, RotateCcw } from 'lucide-react'
import type { ImageGenerationOutput, ImageGenerationTask } from '../../imageCenterModel'
import { imageStatusPresentation } from '../../domain/statusPresentation'
import { OutputCard } from './ImageResultTools'
import { AssetPreview } from './shared/ImageAssets'
function SourceThumb({ file, label, onPreview }: { file: File | null; label: string; onPreview: (file: File, label: string) => void }) {
  return <figure className="image-task-source"><button type="button" disabled={!file} onClick={() => { if (file) onPreview(file, label) }} aria-label={file ? `查看${label}大图` : undefined} title={file ? '查看大图' : undefined}><AssetPreview file={file} alt={file ? `${label}：${file.name}` : ''} /></button><figcaption>{label}</figcaption></figure>
}
export function ImageRecords({ tasks, selectedIds, selectedCompareOutputs, pendingReviewOutputs, onBack, onCreate, onCompare, onBatchReview, recoverUncertainTask, prepareRegeneration, previewSourceImage, toggleOutput, rejectOutput, onPreviewOutput }: {
  tasks: ImageGenerationTask[]
  selectedIds: Set<string>
  selectedCompareOutputs: ImageGenerationOutput[]
  pendingReviewOutputs: ImageGenerationOutput[]
  onBack: () => void
  onCreate: () => void
  onCompare: () => void
  onBatchReview: () => void
  recoverUncertainTask: (task: ImageGenerationTask) => Promise<void>
  prepareRegeneration: (task: ImageGenerationTask) => void
  previewSourceImage: (file: File, label: string) => void
  toggleOutput: (id: string) => void
  rejectOutput: (id: string) => void
  onPreviewOutput: (id: string) => void
}) {
  return <section className="image-records-studio" aria-labelledby="image-records-title">
    <header className="image-records-studio__header">
      <div>
        <button type="button" className="image-studio-back" onClick={onBack}><ArrowLeft size={16} />图片工作室</button>
        <span className="image-studio-home__eyebrow">历史与结果</span>
        <h1 id="image-records-title">生图记录</h1>
        <p>查看进度、审核结果，并把合格画面送入视频生产。</p>
      </div>
      <span className="image-records-studio__badge"><History size={16} />任务结果</span>
    </header>

    <section className="image-results" aria-labelledby="image-results-list-title">
      <div className="image-results-heading"><div><h2 id="image-results-list-title">任务列表</h2><p>当前浏览器已提交的任务会显示在这里，可查看进度、历史结果并直接挑选分镜。</p></div><div className="image-results-heading__actions">{selectedCompareOutputs.length === 2 ? <button type="button" className="secondary-button" onClick={() => onCompare()}><Columns2 size={16} />并排比较</button> : null}{pendingReviewOutputs.length ? <button type="button" className="secondary-button" onClick={() => onBatchReview()}><CheckCircle2 size={16} />批量审核<span className="image-review-count">{pendingReviewOutputs.length}</span></button> : null}<button type="button" className="secondary-button" onClick={onCreate}><Plus size={16} />继续创建</button></div></div>
      {tasks.filter((task) => task.status === 'write_uncertain').map((task) => <div className="image-center-notice is-danger" key={`recovery-${task.id}`} role="status"><AlertTriangle size={16} /><span>{task.outfitName} 的提交结果未知，请先查询服务端原批次。</span><button type="button" className="secondary-button" onClick={() => void recoverUncertainTask(task)}><RotateCcw size={15} />安全查询</button></div>)}
      {!tasks.length ? <div className="image-results-empty"><span><Images size={28} /></span><h3>还没有生图记录</h3><p>提交第一组生图任务后，可在这里查看任务进度和生成结果。</p><button type="button" className="primary-button" onClick={onCreate}>开始创作</button></div> : <div className="image-task-list">{tasks.map((task) => {
        const status = imageStatusPresentation(task.status)
        const active = ['uploading', 'submitting', 'queued', 'running'].includes(task.status)
        return <article id={`image-task-${task.id}`} key={task.id} className="image-task-card"><header><div className="image-task-title"><span><Package size={18} /></span><div><strong>{task.outfitName}</strong><small>{task.sku || new Date(task.createdAt).toLocaleString('zh-CN')}</small></div></div><div className="image-task-header-actions"><div className="image-task-meta"><span>{task.provider === 'gpt' ? 'GPT Image 2' : 'Nano Banana 2'}</span><span>{task.modes.map((mode) => mode === 'fusion' ? '多图融合' : '分镜图').join(' + ')}</span><i className={`is-${status.tone}`}>{active ? <LoaderCircle className="spin" size={13} /> : task.status === 'completed' ? <CheckCircle2 size={13} /> : <Clock3 size={13} />}{status.label}</i></div><button type="button" className="secondary-button image-task-regenerate" onClick={() => prepareRegeneration(task)} title="使用相同素材和配置重新创作"><RotateCcw size={15} />重新生成</button></div></header><div className="image-task-body"><div className="image-task-sources"><SourceThumb file={task.model.front} label="模特正面" onPreview={previewSourceImage} /><SourceThumb file={task.product.front} label="产品正面" onPreview={previewSourceImage} /><SourceThumb file={task.model.back} label="模特背面" onPreview={previewSourceImage} /><SourceThumb file={task.product.back} label="产品背面" onPreview={previewSourceImage} /><SourceThumb file={task.model.side} label="模特侧面" onPreview={previewSourceImage} /><SourceThumb file={task.product.side} label="产品侧面" onPreview={previewSourceImage} /></div>{task.outputs.length ? <div className="image-output-grid">{task.outputs.map((output) => <OutputCard key={output.id} taskId={task.id} output={output} selected={selectedIds.has(output.id)} onToggle={() => void toggleOutput(output.id)} onReject={() => void rejectOutput(output.id)} onPreview={() => onPreviewOutput(output.id)} />)}</div> : <div className={`image-task-waiting${task.error ? ' is-error' : ''}`}><span>{active ? <LoaderCircle className="spin" size={20} /> : <Clock3 size={20} />}</span><div><strong>{task.error ? `${task.errorCode ?? 'GENERATION_FAILED'} · ${task.error}` : status.label}</strong><p>{task.error ? (task.retryable === false ? '该错误不能安全自动重试，请先核对远端任务或联系管理员。' : '可以检查配置后重新提交此套装。') : task.status === 'queued' ? '任务已进入 WaveSpeed 队列。' : task.status === 'running' ? 'WaveSpeed 正在生成图片，页面会自动刷新结果。' : '正在上传参考图并创建远端任务。'}</p></div></div>}</div><details className="image-task-technical"><summary>技术信息<ChevronRight size={14} /></summary><dl><dt>Task ID</dt><dd>{task.id}</dd><dt>Batch ID</dt><dd>{task.batchId ?? '尚未分配'}</dd><dt>Remote Task IDs</dt><dd>{task.providerTaskIds.length ? task.providerTaskIds.join(', ') : '尚未分配'}</dd><dt>Model ID</dt><dd>{task.modelId}</dd>{task.errorCode ? <><dt>错误代码</dt><dd>{task.errorCode}</dd></> : null}</dl></details></article>
      })}</div>}
    </section>
  </section>
}
