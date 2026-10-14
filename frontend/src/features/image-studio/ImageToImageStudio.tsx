import { ImagePlus } from 'lucide-react'
import type { ReactNode } from 'react'
import type { ImageCenterConfig } from '../../imageCenterModel'
import { Button } from '../../shared/components/ui/Button'
import { GenerationConfig } from './shared/GenerationConfig'

export function ImageToImageStudio({ references, config, onChangeConfig, onGenerate, busy, blocked, reason, error, count, saveState }: {
  references: ReactNode
  config: ImageCenterConfig
  onChangeConfig: (config: Partial<ImageCenterConfig>) => void
  onGenerate: () => void
  busy: boolean
  blocked: boolean
  reason: string
  error: string | undefined
  count: number
  saveState: 'saved' | 'saving' | 'error'
}) {
  return <section className="image-quick-studio image-studio-quick" aria-labelledby="image-to-image-title">
    <header className="image-quick-studio__header">
      <h2 id="image-to-image-title">图生图</h2><small className="image-quick-save" role="status">{saveState === 'saved' ? '草稿已保存' : saveState === 'saving' ? '正在保存' : '草稿保存失败'}</small>
    </header>
    {references}
    <div className="image-text-brief">
      <label htmlFor="image-edit-prompt">提示词</label>
      <textarea id="image-edit-prompt" rows={3} maxLength={2800} value={config.fusionPrompt}
        onChange={event => onChangeConfig({ fusionPrompt: event.target.value })}
        placeholder="描述服装细节和画面要求" />
    </div>
    <GenerationConfig config={config} onChange={onChangeConfig} />
    <details className="image-simple-advanced"><summary>高级参数</summary><GenerationConfig config={config} onChange={onChangeConfig} advanced /></details>
    <div className="image-quick-studio__action">
      <div><strong>预计生成 {count} 张图片</strong>{error ? <span className="image-studio-input-error">{error}</span> : null}
        {blocked ? <span role="status">{reason}</span> : null}
      </div>
      <Button variant="primary" icon={<ImagePlus size={17} />} busy={busy} disabled={blocked || Boolean(error)} onClick={onGenerate}>生成图片</Button>
    </div>
  </section>
}
