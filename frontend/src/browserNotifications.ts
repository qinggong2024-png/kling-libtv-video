import type { Task } from './types'

export const BROWSER_NOTIFICATION_PREFERENCE_KEY = 'browser-notifications-enabled'

export type TaskNotification = {
  title: string
  body: string
  tag: string
}

export function readBrowserNotificationPreference(): boolean {
  return localStorage.getItem(BROWSER_NOTIFICATION_PREFERENCE_KEY) !== 'false'
}

export function writeBrowserNotificationPreference(enabled: boolean): void {
  localStorage.setItem(BROWSER_NOTIFICATION_PREFERENCE_KEY, String(enabled))
}

export function taskNotificationForTransition(previousPhase: string | undefined, task: Task): TaskNotification | null {
  if (!previousPhase || previousPhase === task.phase) return null
  if (task.phase === 'AWAITING_CONFIRMATION') {
    return {
      title: '方案等待确认',
      body: `“${task.title}”的生成方案已准备好，请返回确认。`,
      tag: `task:${task.id}:confirmation`,
    }
  }
  if (task.phase === 'DELIVERABLE') {
    return {
      title: '视频生成完成',
      body: `“${task.title}”已生成完成，可以查看或下载。`,
      tag: `task:${task.id}:completed`,
    }
  }
  if (task.phase === 'PARTIALLY_DELIVERABLE') {
    return {
      title: '视频部分完成',
      body: `“${task.title}”已有可用结果，请返回查看。`,
      tag: `task:${task.id}:partially-completed`,
    }
  }
  return null
}

export function shouldCloseTaskNotification(phase: string | undefined, taskIsOpen: boolean): boolean {
  if (taskIsOpen) return true
  return phase !== 'AWAITING_CONFIRMATION'
    && phase !== 'DELIVERABLE'
    && phase !== 'PARTIALLY_DELIVERABLE'
}
