import type { Task } from './types'
import type { ImageGenerationTask, ImageTaskStatus } from './imageCenterModel'

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
  if (task.phase === 'ACTION_REQUIRED') {
    return {
      title: '视频任务需要处理',
      body: `“${task.title}”生成时遇到问题，请返回查看原因。`,
      tag: `task:${task.id}:action-required`,
    }
  }
  if (task.phase === 'CANCELLED') {
    return {
      title: '视频任务已取消',
      body: `“${task.title}”已停止执行。`,
      tag: `task:${task.id}:cancelled`,
    }
  }
  return null
}

export function imageTaskNotificationForTransition(
  previousStatus: ImageTaskStatus | undefined,
  task: ImageGenerationTask,
): TaskNotification | null {
  if (!previousStatus || previousStatus === task.status) return null
  if (task.status === 'completed') {
    const outputSummary = task.outputs.length ? `，共 ${task.outputs.length} 张` : ''
    return {
      title: '图片生成完成',
      body: `“${task.outfitName}”的图片已生成完成${outputSummary}，可以返回查看。`,
      tag: `image-task:${task.id}:completed`,
    }
  }
  if (task.status === 'failed') {
    return {
      title: '图片生成异常',
      body: task.error
        ? `“${task.outfitName}”生成失败：${task.error}`
        : `“${task.outfitName}”生成失败，请返回查看原因。`,
      tag: `image-task:${task.id}:failed`,
    }
  }
  if (task.status === 'write_uncertain') {
    return {
      title: '图片任务状态异常',
      body: `“${task.outfitName}”的提交结果暂时无法确认，请勿重复提交并返回查看。`,
      tag: `image-task:${task.id}:write-uncertain`,
    }
  }
  return null
}

export function shouldCloseTaskNotification(phase: string | undefined, taskIsOpen: boolean): boolean {
  if (taskIsOpen) return true
  return phase !== 'AWAITING_CONFIRMATION'
    && phase !== 'DELIVERABLE'
    && phase !== 'PARTIALLY_DELIVERABLE'
    && phase !== 'ACTION_REQUIRED'
    && phase !== 'CANCELLED'
}
