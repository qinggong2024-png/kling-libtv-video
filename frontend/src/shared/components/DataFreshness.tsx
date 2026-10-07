import { CheckCircle2, Clock3, RefreshCw } from 'lucide-react'

function formatRelativeTime(timestamp: number | null, now = Date.now()) {
  if (!timestamp) return '尚未同步'
  const seconds = Math.max(0, Math.floor((now - timestamp) / 1000))
  if (seconds < 10) return '刚刚同步'
  if (seconds < 60) return `${seconds} 秒前同步`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes} 分钟前同步`
  return `${Math.floor(minutes / 60)} 小时前同步`
}

export function DataFreshness({ timestamp, stale = false }: { timestamp: number | null; stale?: boolean }) {
  return <span className={`data-freshness${stale ? ' is-stale' : ''}`} role="status" aria-live="polite">
    {stale ? <RefreshCw size={14} aria-hidden="true" /> : timestamp ? <CheckCircle2 size={14} aria-hidden="true" /> : <Clock3 size={14} aria-hidden="true" />}
    <span>{stale ? `${formatRelativeTime(timestamp)} · 当前显示上次成功数据` : formatRelativeTime(timestamp)}</span>
  </span>
}
