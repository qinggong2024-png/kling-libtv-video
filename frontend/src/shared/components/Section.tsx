// 本文件由 App.tsx 拆分生成（2026-09-28 前端架构拆分 v2）。
// 代码为逐字搬运，未经逻辑改写。


export function SectionHeading({ title, count, action }: { title: string; count?: number; action?: React.ReactNode }) {
  return <div className="section-heading"><div><h2>{title}</h2>{typeof count === 'number' ? <span className="count-badge">{count}</span> : null}</div>{action}</div>
}

export function EmptyState({ icon, title, description, action }: { icon: React.ReactNode; title: string; description: string; action?: React.ReactNode }) {
  return <div className="empty-state"><span>{icon}</span><strong>{title}</strong><p>{description}</p>{action ? <div className="empty-state-action">{action}</div> : null}</div>
}
