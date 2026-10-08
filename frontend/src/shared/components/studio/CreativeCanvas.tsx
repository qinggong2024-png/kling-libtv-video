import { Expand, Image, RotateCcw } from 'lucide-react'
import { useState } from 'react'
import { LocalImage } from '../Media'
import { IconButton } from '../ui/Button'

export function CreativeCanvas({ file, name, aspectRatio = '9:16', onPreview }: {
  file?: File
  name?: string
  aspectRatio?: string
  onPreview: () => void
}) {
  const [zoom, setZoom] = useState(100)
  const ratio = /^(9:16|16:9|1:1|4:3|3:4)$/.test(aspectRatio) ? aspectRatio.replace(':', '/') : '9/16'
  return <section className="studio-canvas" aria-label="创意画布">
    <header><span><Image size={15} aria-hidden="true" />素材预览</span><div><span>{aspectRatio}</span><IconButton label="打开大图" onClick={onPreview} disabled={!file}><Expand size={16} /></IconButton></div></header>
    <div className="studio-canvas__stage">
      {file ? <div className="studio-canvas__frame" style={{ aspectRatio: ratio, transform: `scale(${zoom / 100})` }}><LocalImage file={file} alt={name ?? file.name} /></div>
        : <div className="studio-canvas__empty"><Image size={34} aria-hidden="true" /><strong>暂无分镜</strong></div>}
    </div>
    <footer><span title={name}>{name ?? '未选择素材'}</span><div><label>缩放<input type="range" min={50} max={150} step={10} value={zoom} disabled={!file} aria-label="画布缩放" onChange={(event) => setZoom(Number(event.target.value))} /></label><output>{zoom}%</output><IconButton label="重置缩放" onClick={() => setZoom(100)} disabled={!file}><RotateCcw size={15} /></IconButton></div></footer>
  </section>
}
