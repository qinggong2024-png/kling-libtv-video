import type { ImageCenterConfig } from '../../../imageCenterModel'

export function GenerationConfig({ config, onChange, advanced = false }: {
  config: ImageCenterConfig
  onChange: (config: Partial<ImageCenterConfig>) => void
  advanced?: boolean
}) {
  return <div className="image-simple-config">
    {advanced ? <>
      <label>模型<select aria-label="模型" value={config.provider} onChange={event => onChange({ provider: event.target.value as ImageCenterConfig['provider'] })}>
        <option value="nanobanana">Nano Banana 2</option><option value="gpt">GPT Image 2</option>
      </select></label>
      <label>分辨率<select aria-label="分辨率" value={config.resolution} onChange={event => onChange({ resolution: event.target.value })}>
        <option value="1k">1K</option><option value="2k">2K</option><option value="4k">4K</option>
      </select></label>
    </> : <>
      <label>比例<select aria-label="比例" value={config.aspectRatio} onChange={event => onChange({ aspectRatio: event.target.value })}>
        {['9:16', '16:9', '1:1', '3:4', '4:3'].map(ratio => <option key={ratio}>{ratio}</option>)}
      </select></label>
      <label>数量<select aria-label="数量" value={config.resultCount} onChange={event => onChange({ resultCount: Number(event.target.value) as ImageCenterConfig['resultCount'] })}>
        {[1, 2, 3, 4].map(count => <option key={count} value={count}>{count}</option>)}
      </select></label>
    </>}
  </div>
}
