import { ImagePlus } from 'lucide-react'
import { Button } from '../../shared/components/ui/Button'

export function TextToImageStudio({ prompt, onChange, saved }: {
  prompt: string
  onChange: (prompt: string) => void
  saved: boolean
}) {
  return <section className="image-quick-studio" aria-labelledby="text-to-image-title">
    <header className="image-quick-studio__header"><h2 id="text-to-image-title">文生图</h2></header>
    <div className="image-text-brief">
      <label htmlFor="image-text-brief-input">提示词</label>
      <textarea id="image-text-brief-input" rows={5} maxLength={2800} value={prompt} onChange={event => onChange(event.target.value)}
        placeholder="描述你想生成的场景、人物和摄影风格" />
      <small role="status">{saved ? '草稿已保存' : '草稿未保存，浏览器存储不可用'}</small>
    </div>
    <div className="image-quick-studio__action">
      <p role="status">当前生图接口要求商品图和人物图，尚未开放纯文本生成。你可以先保存创意草稿。</p>
      <Button variant="primary" icon={<ImagePlus size={17} />} disabled>文生图暂未开放</Button>
    </div>
  </section>
}
