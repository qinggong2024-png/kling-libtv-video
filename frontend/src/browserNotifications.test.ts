import { describe, expect, it } from 'vitest'
import { shouldCloseTaskNotification, taskNotificationForTransition } from './browserNotifications'
import type { Task } from './types'

function task(phase: string): Task {
  return {
    id: 'task-1',
    title: '夏季连衣裙',
    phase,
  } as Task
}

describe('browser task notifications', () => {
  it('does not notify while establishing the initial task baseline', () => {
    expect(taskNotificationForTransition(undefined, task('AWAITING_CONFIRMATION'))).toBeNull()
  })

  it('notifies when a task starts waiting for confirmation', () => {
    expect(taskNotificationForTransition('ANALYZING', task('AWAITING_CONFIRMATION'))).toEqual({
      title: '方案等待确认',
      body: '“夏季连衣裙”的生成方案已准备好，请返回确认。',
      tag: 'task:task-1:confirmation',
    })
  })

  it.each([
    ['DELIVERABLE', '视频生成完成'],
    ['PARTIALLY_DELIVERABLE', '视频部分完成'],
    ['ACTION_REQUIRED', '视频任务需要处理'],
    ['CANCELLED', '视频任务已取消'],
  ])('notifies when a task becomes %s', (phase, title) => {
    expect(taskNotificationForTransition('GENERATING', task(phase))?.title).toBe(title)
  })

  it('ignores unchanged and unrelated phases', () => {
    expect(taskNotificationForTransition('GENERATING', task('GENERATING'))).toBeNull()
    expect(taskNotificationForTransition('ANALYZING', task('PREPARING'))).toBeNull()
  })

  it('closes a notification after the task is opened or leaves the notified phase', () => {
    expect(shouldCloseTaskNotification('AWAITING_CONFIRMATION', true)).toBe(true)
    expect(shouldCloseTaskNotification('PREPARING', false)).toBe(true)
    expect(shouldCloseTaskNotification('AWAITING_CONFIRMATION', false)).toBe(false)
    expect(shouldCloseTaskNotification('DELIVERABLE', false)).toBe(false)
    expect(shouldCloseTaskNotification('ACTION_REQUIRED', false)).toBe(false)
    expect(shouldCloseTaskNotification('CANCELLED', false)).toBe(false)
  })
})
