// 本文件由 App.tsx 拆分生成（2026-09-21 前端架构拆分 v1）。
// 逐字搬运 App() 中的浏览器通知 / 页内 toast / 提示音逻辑，行为不变：
//  - 仅在页面失焦时弹系统通知（document.hidden || !document.hasFocus()）
//  - 任务 phase 变化才推送，首次加载只建立基线不推送
//  - 详情页或图片中心可见时关闭对应通知
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  readBrowserNotificationPreference,
  shouldCloseTaskNotification,
  taskNotificationForTransition,
  writeBrowserNotificationPreference,
} from '../browserNotifications'
import type { ImageCenterNotificationEvent } from '../features/image-studio'
import type { InPageTaskToast, TaskNotificationEvent, View } from './appTypes'

export function browserNotificationPermission(): NotificationPermission | 'unsupported' {
  return 'Notification' in window ? Notification.permission : 'unsupported'
}

type Options = {
  tasks: import('../types').Task[]
  actor: import('../types').AuthUser | null
  detailId: string | null
  view: View
  navigate: (nextView: View, nextDetailId?: string | null) => void
  setImageNotificationTaskId: (taskId: string) => void
}

export function useTaskNotifications({ tasks, actor, detailId, view, navigate, setImageNotificationTaskId }: Options) {
  const [browserNotificationsEnabled, setBrowserNotificationsEnabled] = useState(readBrowserNotificationPreference)
  const [notificationPermission, setNotificationPermission] = useState(browserNotificationPermission)
  const [notificationPromptDismissed, setNotificationPromptDismissed] = useState(false)
  const [inPageTaskToasts, setInPageTaskToasts] = useState<InPageTaskToast[]>([])
  const previousTaskPhasesRef = useRef<Map<string, string>>(new Map())
  const notificationBaselineReadyRef = useRef(false)
  const activeNotificationsRef = useRef<Map<string, Notification>>(new Map())
  const notificationAudioContextRef = useRef<AudioContext | null>(null)

  const enableBrowserNotifications = useCallback(async () => {
    if (!('Notification' in window)) {
      setNotificationPermission('unsupported')
      return
    }
    const permission = Notification.permission === 'default'
      ? await Notification.requestPermission()
      : Notification.permission
    setNotificationPermission(permission)
    if (permission === 'granted') {
      writeBrowserNotificationPreference(true)
      setBrowserNotificationsEnabled(true)
      setNotificationPromptDismissed(false)
    }
  }, [])

  const disableBrowserNotifications = useCallback(() => {
    writeBrowserNotificationPreference(false)
    setBrowserNotificationsEnabled(false)
  }, [])

  useEffect(() => {
    const syncPermission = () => setNotificationPermission(browserNotificationPermission())
    window.addEventListener('focus', syncPermission)
    return () => window.removeEventListener('focus', syncPermission)
  }, [])

  useEffect(() => {
    const unlockNotificationSound = () => {
      if (!notificationAudioContextRef.current) {
        notificationAudioContextRef.current = new AudioContext()
      }
      if (notificationAudioContextRef.current.state === 'suspended') {
        void notificationAudioContextRef.current.resume()
      }
    }
    window.addEventListener('pointerdown', unlockNotificationSound, { once: true })
    window.addEventListener('keydown', unlockNotificationSound, { once: true })
    return () => {
      window.removeEventListener('pointerdown', unlockNotificationSound)
      window.removeEventListener('keydown', unlockNotificationSound)
      const context = notificationAudioContextRef.current
      notificationAudioContextRef.current = null
      if (context) void context.close()
    }
  }, [])

  const playTaskNotificationSound = useCallback((tone: InPageTaskToast['tone']) => {
    const context = notificationAudioContextRef.current
    if (!context || context.state === 'closed') return
    const play = () => {
      const start = context.currentTime + 0.02
      const frequencies = tone === 'success' ? [523.25, 659.25] : [440, 523.25]
      frequencies.forEach((frequency, index) => {
        const oscillator = context.createOscillator()
        const gain = context.createGain()
        const noteStart = start + index * 0.13
        oscillator.type = 'sine'
        oscillator.frequency.setValueAtTime(frequency, noteStart)
        gain.gain.setValueAtTime(0.0001, noteStart)
        gain.gain.exponentialRampToValueAtTime(0.08, noteStart + 0.018)
        gain.gain.exponentialRampToValueAtTime(0.0001, noteStart + 0.18)
        oscillator.connect(gain)
        gain.connect(context.destination)
        oscillator.start(noteStart)
        oscillator.stop(noteStart + 0.2)
      })
    }
    if (context.state === 'suspended') {
      void context.resume().then(play).catch(() => {})
    } else {
      play()
    }
  }, [])

  useEffect(() => {
    if (!inPageTaskToasts.length) return
    const nextExpiry = Math.min(...inPageTaskToasts.map((toast) => toast.expiresAt))
    const timer = window.setTimeout(() => {
      const now = Date.now()
      setInPageTaskToasts((current) => current.filter((toast) => toast.expiresAt > now))
    }, Math.max(0, nextExpiry - Date.now()))
    return () => window.clearTimeout(timer)
  }, [inPageTaskToasts])

  useEffect(() => {
    const closeNotifications = () => {
      for (const notification of activeNotificationsRef.current.values()) notification.close()
      activeNotificationsRef.current.clear()
    }
    window.addEventListener('beforeunload', closeNotifications)
    return () => {
      window.removeEventListener('beforeunload', closeNotifications)
      closeNotifications()
    }
  }, [])

  const presentTaskNotifications = useCallback((events: TaskNotificationEvent[]) => {
    if (!events.length) return
    const now = Date.now()
    const nextToasts = events.map(({ taskId, view: destinationView, payload, tone }) => ({
      id: payload.tag,
      taskId,
      view: destinationView,
      title: payload.title,
      body: payload.body,
      tone,
      expiresAt: now + 5000,
    }))
    setInPageTaskToasts((current) => {
      const replacingIds = new Set(nextToasts.map((toast) => toast.id))
      return [...current.filter((toast) => !replacingIds.has(toast.id)), ...nextToasts].slice(-3)
    })
    playTaskNotificationSound(events.some(({ tone }) => tone === 'warning') ? 'warning' : 'success')

    const pageIsInBackground = document.hidden || !document.hasFocus()
    if (!browserNotificationsEnabled || notificationPermission !== 'granted' || !pageIsInBackground) return
    for (const { notificationKey, taskId, view: destinationView, payload } of events) {
      activeNotificationsRef.current.get(notificationKey)?.close()
      const notification = new Notification(payload.title, {
        body: payload.body,
        tag: payload.tag,
        icon: '/favicon.svg',
      })
      activeNotificationsRef.current.set(notificationKey, notification)
      notification.onclose = () => {
        if (activeNotificationsRef.current.get(notificationKey) === notification) {
          activeNotificationsRef.current.delete(notificationKey)
        }
      }
      notification.onclick = () => {
        notification.close()
        activeNotificationsRef.current.delete(notificationKey)
        window.focus()
        if (destinationView === 'images') setImageNotificationTaskId(taskId)
        navigate(destinationView, destinationView === 'make' ? taskId : null)
      }
    }
  }, [browserNotificationsEnabled, navigate, notificationPermission, playTaskNotificationSound, setImageNotificationTaskId])

  const handleImageNotifications = useCallback((events: ImageCenterNotificationEvent[]) => {
    presentTaskNotifications(events.map(({ taskId, status, notification }) => ({
      notificationKey: `image:${taskId}`,
      taskId,
      view: 'images' as const,
      payload: notification,
      tone: status === 'completed' ? 'success' as const : 'warning' as const,
    })))
  }, [presentTaskNotifications])

  useEffect(() => {
    if (!actor) {
      previousTaskPhasesRef.current.clear()
      notificationBaselineReadyRef.current = false
      for (const notification of activeNotificationsRef.current.values()) notification.close()
      activeNotificationsRef.current.clear()
      return
    }
    if (!notificationBaselineReadyRef.current) {
      previousTaskPhasesRef.current = new Map(tasks.map((task) => [task.id, task.phase]))
      notificationBaselineReadyRef.current = true
      return
    }

    const previousPhases = previousTaskPhasesRef.current
    const nextPhases = new Map(tasks.map((task) => [task.id, task.phase]))
    for (const [notificationKey, notification] of activeNotificationsRef.current) {
      if (!notificationKey.startsWith('video:')) continue
      const taskId = notificationKey.slice('video:'.length)
      const phase = nextPhases.get(taskId)
      if (shouldCloseTaskNotification(phase, taskId === detailId)) {
        notification.close()
        activeNotificationsRef.current.delete(notificationKey)
      }
    }
    const transitions = tasks.flatMap((task): TaskNotificationEvent[] => {
      const payload = taskNotificationForTransition(previousPhases.get(task.id), task)
      if (!payload) return []
      const tone: InPageTaskToast['tone'] = task.phase === 'DELIVERABLE' ? 'success' : 'warning'
      return [{
        notificationKey: `video:${task.id}`,
        taskId: task.id,
        view: 'make',
        payload,
        tone,
      }]
    })
    presentTaskNotifications(transitions)
    previousTaskPhasesRef.current = nextPhases
  }, [actor, detailId, presentTaskNotifications, tasks])

  useEffect(() => {
    if (!detailId) return
    const closeSelectedNotification = () => {
      if (document.hidden || !document.hasFocus()) return
      const notificationKey = `video:${detailId}`
      activeNotificationsRef.current.get(notificationKey)?.close()
      activeNotificationsRef.current.delete(notificationKey)
    }
    closeSelectedNotification()
    window.addEventListener('focus', closeSelectedNotification)
    document.addEventListener('visibilitychange', closeSelectedNotification)
    return () => {
      window.removeEventListener('focus', closeSelectedNotification)
      document.removeEventListener('visibilitychange', closeSelectedNotification)
    }
  }, [detailId])

  useEffect(() => {
    if (view !== 'images') return
    const closeImageNotifications = () => {
      if (document.hidden || !document.hasFocus()) return
      for (const [notificationKey, notification] of activeNotificationsRef.current) {
        if (!notificationKey.startsWith('image:')) continue
        notification.close()
        activeNotificationsRef.current.delete(notificationKey)
      }
    }
    closeImageNotifications()
    window.addEventListener('focus', closeImageNotifications)
    document.addEventListener('visibilitychange', closeImageNotifications)
    return () => {
      window.removeEventListener('focus', closeImageNotifications)
      document.removeEventListener('visibilitychange', closeImageNotifications)
    }
  }, [view])

  return {
    browserNotificationsEnabled,
    notificationPermission,
    notificationPromptDismissed,
    setNotificationPromptDismissed,
    inPageTaskToasts,
    setInPageTaskToasts,
    enableBrowserNotifications,
    disableBrowserNotifications,
    handleImageNotifications,
  }
}
