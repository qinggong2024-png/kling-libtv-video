import { Film, SlidersHorizontal } from 'lucide-react'
import { useId, useState } from 'react'
import type { VideoTemplateSummary } from '../../../types'
import { FoundationDrawer, FoundationStatusBadge } from '../ui'
import { Button } from '../ui/Button'

export function TemplateCard({ template, onPreview }: { template: VideoTemplateSummary; onPreview: () => void }) {
  return <article className="studio-template-card">
    <div className="studio-template-card__title"><Film size={18} aria-hidden="true" /><strong>{template.name}</strong><FoundationStatusBadge status={{ label: template.status === 'active' ? '可用' : '待验收', tone: template.status === 'active' ? 'success' : 'warning' }} /></div>
    <p>{template.description}</p>
    <div className="studio-template-card__meta"><span>{template.defaultSettings.ratio}</span><span>{template.minImages}–{template.maxImages} 张分镜</span><span>v{template.version}</span></div>
    <Button variant="ghost" icon={<SlidersHorizontal size={15} aria-hidden="true" />} onClick={onPreview}>查看配方</Button>
  </article>
}

export function RecipePreview({ template }: { template: VideoTemplateSummary }) {
  const groups = [
    { name: '动作', presets: template.actionPresets },
    { name: '镜头', presets: template.cameraPresets },
    { name: '节奏', presets: template.tempoPresets },
  ]
  return <div className="studio-recipe">
    <p>{template.description}</p>
    <dl><dt>默认画幅</dt><dd>{template.defaultSettings.ratio}</dd><dt>默认时长</dt><dd>{template.defaultSettings.durationSeconds} 秒</dd><dt>分镜数量</dt><dd>{template.minImages}–{template.maxImages}</dd></dl>
    {groups.map(({ name, presets }) => <section key={name}><h3>{name}</h3>{Object.values(presets).length
      ? Object.entries(presets).map(([id, preset]) => <div key={id}><strong>{preset.label}</strong><p>{preset.instruction}</p></div>)
      : <p>未配置</p>}</section>)}
    {template.sourceNote ? <p className="studio-recipe__source">{template.sourceNote}</p> : null}
  </div>
}

export function TemplateSelector({ templates, value, onChange, disabled = false, loading = false, compact = false }: {
  templates: VideoTemplateSummary[]
  value: string
  onChange: (value: string) => void
  disabled?: boolean
  loading?: boolean
  compact?: boolean
}) {
  const id = useId()
  const [previewOpen, setPreviewOpen] = useState(false)
  const selected = templates.find((template) => template.id === value)
  return <section className={`studio-template-selector${compact ? ' studio-template-selector--compact' : ''}`} aria-label="视频模板">
    <label htmlFor={id}>视频模板</label>
    <div className="studio-template-controls">
      <select id={id} value={value} disabled={disabled || loading} onChange={(event) => onChange(event.target.value)}>
        {!templates.length ? <option value="">{loading ? '正在读取模板' : '暂无可用模板'}</option> : null}
        {templates.map((template) => <option key={template.id} value={template.id}>{template.name}{template.status !== 'active' ? ' · 待验收' : ''}</option>)}
      </select>
      {compact && selected ? <Button variant="ghost" icon={<SlidersHorizontal size={15} aria-hidden="true" />} onClick={() => setPreviewOpen(true)}>查看配方</Button> : null}
    </div>
    {selected ? compact ? <div className="studio-template-summary">
      <FoundationStatusBadge status={{ label: selected.status === 'active' ? '可用' : '待验收', tone: selected.status === 'active' ? 'success' : 'warning' }} />
      <span>{selected.defaultSettings.ratio}</span><span>{selected.minImages}–{selected.maxImages} 张分镜</span>
    </div> : <TemplateCard template={selected} onPreview={() => setPreviewOpen(true)} /> : null}
    <FoundationDrawer open={previewOpen && Boolean(selected)} title={selected?.name ?? '模板配方'} onClose={() => setPreviewOpen(false)}>
      {selected ? <RecipePreview template={selected} /> : null}
    </FoundationDrawer>
  </section>
}
