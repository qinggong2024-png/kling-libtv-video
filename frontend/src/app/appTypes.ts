// 本文件由 App.tsx 拆分生成（2026-09-28 前端架构拆分 v2）。
// 代码为逐字搬运，未经逻辑改写。
import { type TaskNotification } from '../browserNotifications'

export type View = 'images' | 'make' | 'records' | 'library' | 'admin' | 'settings'
export type RecordsFilter = 'all' | 'attention' | 'active' | 'partial' | 'done' | 'failed' | 'cancelled'
export type AdminSection = 'overview' | 'accounts' | 'providers' | 'security'
export type InPageTaskToast = {
  id: string
  taskId: string
  view: 'images' | 'make'
  title: string
  body: string
  tone: 'success' | 'warning'
  expiresAt: number
}
export type TaskNotificationEvent = {
  notificationKey: string
  taskId: string
  view: 'images' | 'make'
  payload: TaskNotification
  tone: InPageTaskToast['tone']
}
