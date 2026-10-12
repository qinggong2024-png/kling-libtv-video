import { ArrowRight, BookOpen, FolderOpen, Pencil, Save, Shirt } from 'lucide-react'
import { useState } from 'react'
import type { ProductSurface } from '../../app/productNavigation'
import { useOptionalCreativeProject } from '../../creative-project/hooks'
import type { Task } from '../../types'
import { Button, IconButton } from '../../shared/components/ui/Button'
import { FoundationDrawer } from '../../shared/components/ui'
import { CreativePanel, CreativeReviewSummary, CreativeStatus, CreativeSteps } from '../../shared/components/studio/CreativeFoundation'
import { presentCreativeWorkspace } from './workspacePresentation'

export function ProjectContextBar({ tasks, onNavigate }: { tasks?: readonly Task[]; onNavigate: (surface: ProductSurface) => void }) {
  const context = useOptionalCreativeProject()
  if (!context) return null
  const summary = presentCreativeWorkspace(context.project, tasks)
  return <div className="creative-context-bar" aria-label="当前项目">
    <button type="button" className="creative-project-link" title="查看当前项目" onClick={() => onNavigate('workspace')}><FolderOpen size={17} /><span>{context.project.name || '未命名项目'}</span><ArrowRight size={14} /></button>
    <CreativeStatus value={summary.status} />
  </div>
}

export function CreativeWorkspaceView({ surface, tasks, onNavigate }: { surface: 'workspace' | 'projects' | 'memory'; tasks: readonly Task[]; onNavigate: (surface: ProductSurface) => void }) {
  const context = useOptionalCreativeProject()
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState('')
  if (!context) return <section className="creative-workspace-view"><h1>Creative Workspace</h1><p>当前项目尚未加载。</p></section>
  const project = context.project
  const summary = presentCreativeWorkspace(project, tasks)
  const openEditor = () => { setName(project.name ?? ''); setEditing(true) }
  const title = surface === 'projects' ? '项目' : surface === 'memory' ? 'Creative Memory' : 'Creative Workspace'
  const recovery = project.workflowContext

  return <section className="creative-workspace-view" aria-label={title}>
    <header className="creative-workspace-heading">
      <div><span className="creative-workspace-kicker">{surface === 'projects' ? '项目' : surface === 'memory' ? '规划记录' : '当前创作'}</span><h1>{surface === 'workspace' ? project.name || '未命名项目' : title}</h1></div>
      <div className="creative-workspace-tools">
        <CreativeStatus value={summary.status} />
        {surface !== 'memory' ? <IconButton label="规划记录" onClick={() => onNavigate('memory')}><BookOpen size={17} /></IconButton> : <IconButton label="返回当前项目" onClick={() => onNavigate('workspace')}><FolderOpen size={17} /></IconButton>}
        <IconButton label="编辑项目名称" onClick={openEditor}><Pencil size={17} /></IconButton>
      </div>
    </header>
    {surface === 'projects' ? <>
      <CreativePanel title="当前项目" subtitle="当前浏览器的项目与规划记录">
        <article className="creative-project-item">
          <FolderOpen size={25} /><div><h2>{project.name || '未命名项目'}</h2><p>{summary.planning?.brief.productName || '尚未填写商品'}</p><CreativeStatus value={summary.status} /></div>
          <Button variant="primary" icon={<ArrowRight size={16} />} onClick={() => onNavigate('workspace')}>打开工作区</Button>
        </article>
      </CreativePanel>
    </> : surface === 'memory' ? <>
      <CreativePanel title="规划记录" subtitle={project.name || '未命名项目'}>
        <dl className="creative-overview-list">
          <div><dt>创意方向</dt><dd>{summary.direction?.title ?? '尚未选择'}</dd></div>
          <div><dt>生产包版本</dt><dd>{summary.pkg ? `${summary.pkg.packageId} · r${summary.pkg.revision}` : '尚无生产包'}</dd></div>
          <div><dt>桥接决定</dt><dd>{summary.bridge ? '待预检 · 真实提交关闭' : '尚无桥接上下文'}</dd></div>
          <div><dt>恢复引用</dt><dd>{recovery?.creativeTaskId ?? '尚无导演任务引用'}</dd></div>
        </dl>
        <CreativeReviewSummary>这里只展示已保存的项目规划。审核记录以 Studio 和服务端任务证据为准。</CreativeReviewSummary>
        <Button icon={<BookOpen size={16} />} onClick={() => onNavigate('director')}>查看导演证据</Button>
      </CreativePanel>
    </> : <>
      <section className="creative-next-action" aria-label="下一步">
        <div><span>下一步</span><h2>{summary.nextAction.label}</h2><p>{summary.nextAction.description}</p></div>
        <Button variant="primary" icon={<ArrowRight size={17} />} onClick={() => onNavigate(summary.nextAction.surface)}>{summary.nextAction.label}</Button>
      </section>
      <CreativePanel title="创意概览">
        <dl className="creative-overview-list">
          <div><dt><Shirt size={15} />商品</dt><dd>{summary.planning?.brief.productName || '待输入商品'}</dd></div>
          <div><dt>目标受众</dt><dd>{summary.planning?.brief.audience || '待填写'}</dd></div>
          <div><dt>创意方向</dt><dd>{summary.direction?.title || '待选择'}</dd></div>
        </dl>
      </CreativePanel>
      <CreativePanel title="生产路径" subtitle="已记录证据与当前操作入口">
        <CreativeSteps steps={summary.steps} onOpen={(id) => {
          const step = summary.steps.find((item) => item.id === id)
          if (step) onNavigate(step.surface)
        }} />
        <p className="creative-progress-caption">{summary.steps.filter((step) => step.evidenced).length} / 5 个阶段有记录 · 不是生成进度或交付资格</p>
      </CreativePanel>
      {summary.pkg ? <CreativePanel title="当前生产包" action={<Button variant="ghost" icon={<ArrowRight size={16} />} onClick={() => onNavigate('director')}>查看证据</Button>}>
        <dl className="creative-overview-list"><div><dt>版本</dt><dd>r{summary.pkg.revision} · {summary.pkg.shotId}</dd></div><div><dt>方向</dt><dd>{summary.direction?.title ?? '未提供'}</dd></div><div><dt>生产预检</dt><dd>待服务端验证</dd></div></dl>
        <CreativeReviewSummary>离线规划与 Fake 候选不可交付。真实 Provider 提交保持关闭。</CreativeReviewSummary>
      </CreativePanel> : null}
    </>}
    {editing ? <FoundationDrawer open title="项目设置" onClose={() => setEditing(false)}>
      <form className="creative-project-form" onSubmit={(event) => {
        event.preventDefault()
        if (!name.trim()) return
        context.updateProject({ name: name.trim() })
        setEditing(false)
      }}>
        <label htmlFor="creative-project-name">项目名称</label><input id="creative-project-name" value={name} onChange={(event) => setName(event.target.value)} maxLength={120} required autoFocus />
        <Button variant="primary" type="submit" icon={<Save size={16} />} disabled={!name.trim()}>保存项目名称</Button>
      </form>
    </FoundationDrawer> : null}
  </section>
}
