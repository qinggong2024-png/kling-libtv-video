// 本文件由 App.tsx 拆分生成（2026-09-28 前端架构拆分 v2）。
// 代码为逐字搬运，未经逻辑改写。
import {useEffect} from 'react'
import {type SystemStatus} from '../../types'
import {removeStorage, writeStorage} from '../../safeStorage'
import {BrowserNotificationSetting} from './BrowserNotificationSetting'
import {PersonalPasswordSetting, PersonalPromptConfirmationSetting, PersonalVideoLearningSetting} from './PersonalSettings'
import {AIDailyBudget} from './AIDailyBudget'
import {ContentLibraryView} from '../library/ContentLibraryView'

export function SettingsView({
  system,
  actorId,
  canDeleteSubjects,
  canEditCatalog,
  onLogout,
  browserNotificationsEnabled,
  browserNotificationPermission,
  onEnableBrowserNotifications,
  onDisableBrowserNotifications,
}: {
  system: SystemStatus | null
  actorId: string | null
  canDeleteSubjects: boolean
  canEditCatalog: boolean
  onLogout: () => void
  browserNotificationsEnabled: boolean
  browserNotificationPermission: NotificationPermission | 'unsupported'
  onEnableBrowserNotifications: () => Promise<void>
  onDisableBrowserNotifications: () => void
}) {
  useEffect(() => {
    writeStorage('local', 'generation-provider', 'kling')
    removeStorage('local', 'default-model')
    removeStorage('local', ['default-output-variants', 'video-direction', 'default-ratio', 'default-duration', 'max-concurrency', 'retry-count', 'save-directory'])
  }, [])
  return <div className="page-view settings-view"><div className="page-title"><div><span>个人工作区</span><h1>偏好设置</h1><p>这里只保留会影响你个人工作流的选项；生成模型、API 通道与固定生产规格由管理员统一维护。</p></div><div className="page-title-actions">{system?.sharedAuthentication ? <button className="secondary-button" onClick={onLogout}>退出登录</button> : null}</div></div>
    <AIDailyBudget />
    {system?.sharedAuthentication ? <PersonalPasswordSetting /> : null}
    <PersonalVideoLearningSetting />
    <PersonalPromptConfirmationSetting />
    <BrowserNotificationSetting
      enabled={browserNotificationsEnabled}
      permission={browserNotificationPermission}
      onEnable={onEnableBrowserNotifications}
      onDisable={onDisableBrowserNotifications}
    />
    <ContentLibraryView
      embedded
      actorId={actorId}
      canDeleteSubjects={canDeleteSubjects}
      canEditCatalog={canEditCatalog}
    />
  </div>
}
