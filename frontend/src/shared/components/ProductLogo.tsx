// 本文件由 App.tsx 拆分生成（2026-09-28 前端架构拆分 v2）。
// 代码为逐字搬运，未经逻辑改写。
import { Clapperboard } from 'lucide-react'

export function ProductLogo({ subtitle = 'AI 视频生产' }: { subtitle?: string }) {
  return <span className="brand-lockup"><span className="brand-mark"><Clapperboard size={19} /></span><span><strong>衣影工坊</strong><small title={subtitle}>{subtitle}</small></span></span>
}
