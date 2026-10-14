// 应用入口（2026-09-21 前端架构拆分 v1）。
// 只负责：Provider 组合 + 导航 + 视图分发 + 认证边界。
// 不含 API 调用、不含轮询/通知/生产流程实现（分别在
// features/production/hooks 与 app/use*.ts）。
//
// ★ 代码分割说明（勿改动语义）：
//   admin / settings / library 用 React.lazy 做页面级分割，仅当对应 view 被打开时才拉取。
//   ImageStudio 也走了 dynamic import，但它 **必须保持无条件挂载** —— 它靠在非激活时
//   继续轮询来推送图片任务完成通知（onNotifications / onActiveTasksChange）。
//   因此它被包在 <Suspense fallback={null}> 里且不放进任何条件分支；
//   一旦改成 {view === 'images' ? <ImageStudio/> : null}，非激活期轮询与通知会直接丢失。
import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Bell, Clapperboard, Images, Library, ListVideo, LoaderCircle, RefreshCw, Settings, ShieldCheck, WandSparkles, X } from 'lucide-react'
import { logout } from '../api'
import { ACTIVE_PHASES } from '../domain/workflowStates'
import { LoginScreen } from '../features/auth/LoginScreen'
import { ImageVideoComposerSheet } from '../features/production/ImageVideoComposerSheet'
import { useProductionActions } from '../features/production/hooks/useProductionActions'
import { useTaskPolling } from '../features/production/hooks/useTaskPolling'
import { RecordsView } from '../features/task-center/RecordsView'
import { ImageBatchRecords } from '../features/task-center/ImageBatchRecords'
import { CreativeWorkspaceView, ProjectContextBar } from '../features/creative-workspace/CreativeWorkspaceView'
import { providerPresentation } from '../providerPresentation'
import { writeStorage } from '../safeStorage'
import { InPageTaskToasts } from '../shared/components/InPageTaskToasts'
import { VideoPreview } from '../shared/components/Media'
import { FoundationDrawer } from '../shared/components/ui'
import { AppShell } from './AppShell'
import type { NavItem } from './AppShell'
import { useAppNavigation } from './useAppNavigation'
import { useTaskNotifications } from './useTaskNotifications'
import type { View } from './appTypes'
import { useGeneratedHistory } from './useGeneratedHistory'

// 页面级 lazy：只在进入对应 view 时才下载该页面 chunk。
const ImageStudio = lazy(() => import('../features/image-studio').then((m) => ({ default: m.ImageStudio })))
const GeneratedAssetsView = lazy(() => import('../features/library/GeneratedAssetsView').then((m) => ({ default: m.GeneratedAssetsView })))
const AdminCenterView = lazy(() => import('../features/admin/AdminCenterView').then((m) => ({ default: m.AdminCenterView })))
const SettingsView = lazy(() => import('../features/settings/SettingsView').then((m) => ({ default: m.SettingsView })))
const HomeView = lazy(() => import('../features/task-center/HomeView').then((m) => ({ default: m.HomeView })))
const CreativeWorkspace = lazy(() => import('../features/production/ProductionWorkspace').then((m) => ({ default: m.CreativeWorkspace })))

function PageLoading() {
  return <div className="page-loading"><LoaderCircle className="spin" size={26} /><strong>正在加载页面</strong></div>
}

function App() {
  const { view, surface, detailId, adminSection, recordsFilter, recordsQuery, recordsRestoreScroll, setRecordsRestoreScroll, navigate, navigateSurface, navigateRecords, openTaskFromRecords, closeTaskDetail } = useAppNavigation()
  const [sidebarInfo, setSidebarInfo] = useState<'account' | 'help' | null>(null)
  const [hasActiveImageTasks, setHasActiveImageTasks] = useState(false)
  const [imageNotificationTaskId, setImageNotificationTaskId] = useState<string | null>(null)

  const {
    tasks, setTasks,
    system, actor, setActor,
    devActorRole, setDevActorRole,
    loading, setLoading,
    authRequired, setAuthRequired,
    error, setError,
    lastSyncedAt,
    nextTaskCursor, setNextTaskCursor,
    loadingMoreTasks, setLoadingMoreTasks,
    refreshTasks, refresh,
  } = useTaskPolling(detailId)

  const history = useGeneratedHistory(loading || authRequired ? null : actor?.userId ?? null, view === 'records' || view === 'library')
  const imageBatches = history.images.items
  const assetTasks = history.videos.items
  const directorTasks = history.directors.items

  const {
    browserNotificationsEnabled,
    notificationPermission,
    notificationPromptDismissed,
    setNotificationPromptDismissed,
    inPageTaskToasts,
    setInPageTaskToasts,
    enableBrowserNotifications,
    disableBrowserNotifications,
    handleImageNotifications,
  } = useTaskNotifications({ tasks, actor, detailId, view, navigate, setImageNotificationTaskId })

  const {
    video, setVideo,
    seed,
    imageComposerSeed,
    remixStage,
    taskChanged,
    loadMoreTasks,
    remix,
    reuseCompleted,
    prepareImageCenterVideos,
    play,
    created,
    imageComposerCreated,
    closeImageComposer,
    feedbackChanged,
  } = useProductionActions({
    detailId,
    nextTaskCursor,
    loadingMoreTasks,
    setLoadingMoreTasks,
    setNextTaskCursor,
    setTasks,
    refreshTasks,
    setError,
    navigate,
  })

  const switchView = useCallback((next: View) => {
    navigate(next)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }, [navigate])

  useEffect(() => {
    if (!['records', 'library'].includes(view) || recordsRestoreScroll === null) return
    const frame = window.requestAnimationFrame(() => {
      window.scrollTo({ top: recordsRestoreScroll, behavior: 'auto' })
      setRecordsRestoreScroll(null)
    })
    return () => window.cancelAnimationFrame(frame)
  }, [recordsRestoreScroll, setRecordsRestoreScroll, view])

  const switchDevelopmentActor = useCallback(() => {
    const next = devActorRole === 'admin' ? 'user' : 'admin'
    writeStorage('local', 'development-actor-role', next)
    setDevActorRole(next)
    setSidebarInfo(null)
    setLoading(true)
  }, [devActorRole, setDevActorRole, setLoading])

  const signOut = useCallback(async () => {
    try { await logout() } catch { /* 本地状态仍会回到登录边界。 */ }
    setActor(null)
    setTasks([])
    setSidebarInfo(null)
    setAuthRequired(true)
  }, [setActor, setAuthRequired, setTasks])

  const selectedTask = tasks.find((task) => task.id === detailId) ?? null
  const counts = useMemo(() => ({
    attention: tasks.filter((task) => task.phase === 'AWAITING_CONFIRMATION').length,
    active: tasks.filter((task) => ACTIVE_PHASES.has(task.phase)).length,
  }), [tasks])
  const showNotificationPrompt = browserNotificationsEnabled
    && notificationPermission === 'default'
    && !notificationPromptDismissed
    && (hasActiveImageTasks || tasks.some((task) => ACTIVE_PHASES.has(task.phase) || task.phase === 'AWAITING_CONFIRMATION'))

  if (loading && !actor && !authRequired) {
    return <main className="app-boot-screen"><div role="status" aria-label="正在连接生产服务"><LoaderCircle className="spin" size={22} /></div></main>
  }

  if (system?.sharedAuthentication && authRequired) {
    return <LoginScreen onAuthenticated={async () => { setLoading(true); await refresh() }} />
  }

  const canOperate = actor?.role === 'ADMIN' || actor?.role === 'OPERATOR'
  const currentVideoGeneration = system?.videoGeneration ?? system?.kling
  const currentProviderLabel = system
    ? providerPresentation(currentVideoGeneration?.provider).displayLabel
    : 'AI 视频生产'
  const nav: NavItem[] = [
    { id: 'director-studio', value: 'images', label: '导演台', icon: <WandSparkles size={18} />, surface: 'director' },
    { id: 'image-studio', value: 'images', label: '图片工作室', icon: <Images size={18} />, surface: 'image' },
    { id: 'video-studio', value: 'make', label: '视频工作室', icon: <Clapperboard size={18} />, surface: 'video' },
    { id: 'task-center', value: 'records', label: '任务中心', icon: <ListVideo size={18} />, badge: counts.attention || counts.active },
    { id: 'generated-assets', value: 'library', label: '生成资产', icon: <Library size={18} />, surface: 'assets' },
    ...(canOperate ? [{ id: 'admin', value: 'admin' as const, label: '管理', icon: <ShieldCheck size={18} /> }] : []),
    { id: 'settings', value: 'settings', label: '设置', icon: <Settings size={18} /> },
  ]
  const actorId = system?.sharedAuthentication ? null : actor?.userId ?? null
  const isCreativeWorkspaceSurface = surface === 'workspace' || surface === 'projects' || surface === 'memory'

  const overlays = <>
    <InPageTaskToasts
      toasts={inPageTaskToasts}
      onOpen={(toast) => {
        setInPageTaskToasts((current) => current.filter((item) => item.id !== toast.id))
        if (toast.view === 'images') setImageNotificationTaskId(toast.taskId)
        navigate(toast.view, toast.view === 'make' ? toast.taskId : null)
      }}
      onDismiss={(id) => setInPageTaskToasts((current) => current.filter((toast) => toast.id !== id))}
    />
    {video ? <VideoPreview artifactId={video.artifactId} title={video.title} onClose={() => setVideo(null)} /> : null}
    {imageComposerSeed ? <ImageVideoComposerSheet seed={imageComposerSeed} system={system} actorId={actorId} onClose={closeImageComposer} onCreated={imageComposerCreated} /> : null}
    {remixStage ? <div className="global-loading"><LoaderCircle className="spin" size={20} /><span>{remixStage === 'reuse' ? '正在复用素材和提示词并提交生成' : '正在加载原素材'}</span></div> : null}
  </>

  return <AppShell
    nav={nav}
    view={view}
    onSwitchView={switchView}
    onSwitchSurface={navigateSurface}
    actor={actor}
    system={system}
    error={error}
    currentProviderLabel={currentProviderLabel}
    surface={surface}
    sidebarInfo={sidebarInfo}
    onSidebarInfoChange={setSidebarInfo}
    devActorRole={devActorRole}
    onSwitchDevelopmentActor={switchDevelopmentActor}
    onSignOut={() => void signOut()}
    errorResetKeys={[view, adminSection, selectedTask?.id]}
    onErrorBack={() => navigate('make')}
    projectContext={!isCreativeWorkspaceSurface && view !== 'admin' && view !== 'settings'
      ? <ProjectContextBar tasks={tasks} onNavigate={navigateSurface} />
      : null}
    overlays={overlays}
  >
    {loading ? <PageLoading /> : <>
      {error ? <div className="service-banner"><AlertTriangle size={18} /><span>{error}</span><button onClick={() => void refresh()}><RefreshCw size={15} />重新连接</button></div> : null}
      {showNotificationPrompt ? <div className="notification-permission-banner" role="region" aria-label="浏览器通知">
        <Bell size={18} />
        <span><strong>后台进度提醒</strong><small>开启通知，图片或视频完成、异常以及方案待确认时会及时提醒你。</small></span>
        <button className="secondary-button" type="button" onClick={() => void enableBrowserNotifications()}>开启通知</button>
        <button className="icon-button" type="button" aria-label="暂不开启通知" title="暂不开启" onClick={() => setNotificationPromptDismissed(true)}><X size={17} /></button>
      </div> : null}
      <Suspense fallback={null}>
        <ImageStudio
          active={view === 'images'}
          initialMode={surface === 'director' ? 'director' : surface === 'image' ? 'custom' : undefined}
          draftScope={actor?.userId ?? null}
          openTaskId={imageNotificationTaskId}
          onPrepareVideos={prepareImageCenterVideos}
          onNotifications={handleImageNotifications}
          onActiveTasksChange={setHasActiveImageTasks}
        />
      </Suspense>
      {/* make 是默认落地视图。它同时走 lazy 是为了把 entry chunk 压到 300 kB 以下
          （方案验收线）。代价：应用打开时多一次页面级加载（此前已有 boot screen，
          局域网内可忽略）。若不接受这次可见变化，把 HomeView / CreativeWorkspace
          改回顶部静态 import 并删掉本 Suspense 即可，entry 会回到约 333 kB。 */}
      <Suspense fallback={<PageLoading />}>
        <HomeView active={view === 'make' && !isCreativeWorkspaceSurface} tasks={tasks} seed={seed} system={system} actorId={actorId} canReview={actor?.role === 'ADMIN' || actor?.role === 'OPERATOR'} cutflowCanWrite={Boolean(actor && ['ADMIN', 'OPERATOR', 'USER'].includes(actor.role))} onCreated={created} onOpen={(task) => navigate('make', task.id)} onView={switchView} onPlay={play} onRemix={(task) => void remix(task)} onFeedbackChanged={feedbackChanged} />
        {isCreativeWorkspaceSurface
          ? <CreativeWorkspaceView surface={surface} tasks={tasks} onNavigate={navigateSurface} />
          : null}
        {view === 'make' && surface === null && selectedTask ? <FoundationDrawer open title={selectedTask.title} eyebrow="视频任务" onClose={closeTaskDetail}><div className="studio-task-detail"><CreativeWorkspace key={`${selectedTask.id}-${selectedTask.phase}`} task={selectedTask} onClose={closeTaskDetail} onChanged={taskChanged} onRemix={() => void remix(selectedTask)} onReuse={(variants) => void reuseCompleted(selectedTask, variants)} onPlay={(variant) => play(selectedTask, variant)} /></div></FoundationDrawer> : null}
      </Suspense>
      {view === 'records' ? <RecordsView tasks={tasks} directorTasks={directorTasks} hasMore={Boolean(nextTaskCursor)} loadingMore={loadingMoreTasks} lastSyncedAt={lastSyncedAt} syncError={Boolean(error)} onLoadMore={() => void loadMoreTasks()} onOpen={(task) => openTaskFromRecords(task.id)} onPlay={play} onRemix={(task) => void remix(task)} onFeedbackChanged={feedbackChanged} onCreateTask={() => navigate('make')} canReview={actor?.role === 'ADMIN' || actor?.role === 'OPERATOR'} cutflowEnabled={system?.cutflowHandoffEnabled} cutflowCanWrite={Boolean(actor && ['ADMIN', 'OPERATOR', 'USER'].includes(actor.role))} initialFilter={recordsFilter} initialQuery={recordsQuery} onStateChange={navigateRecords} /> : null}
      {view === 'records' || view === 'library' ? <div aria-label="历史同步状态">
        {([['图片', history.images], ['视频', history.videos], ['导演', history.directors]] as const).map(([label, source]) => source.error
          ? <div key={label} className="service-banner" role="alert"><AlertTriangle size={18} /><span>{label}历史读取失败：{source.error}</span><button type="button" onClick={history.refreshHistory}><RefreshCw size={15} />重试</button></div>
          : source.loading && !source.syncedAt ? <div key={label} role="status">正在读取{label}历史</div> : null)}
      </div> : null}
      {view === 'records' ? <ImageBatchRecords batches={imageBatches} query={recordsQuery} onChanged={() => { history.refreshHistory(); void refreshTasks() }} /> : null}
      {view === 'library' ? <Suspense fallback={<PageLoading />}><GeneratedAssetsView
        tasks={assetTasks}
        imageBatches={imageBatches}
        lastSyncedAt={history.videos.syncedAt}
        syncError={Boolean(history.images.error || history.videos.error)}
        onOpen={(task) => openTaskFromRecords(task.id)}
        onPlay={play}
        onRemix={(task) => void remix(task)}
        onFeedbackChanged={(task) => { feedbackChanged(task); history.refreshHistory() }}
        onCreateTask={() => navigate('make')}
        canReview={actor?.role === 'ADMIN' || actor?.role === 'OPERATOR'}
        cutflowEnabled={system?.cutflowHandoffEnabled}
        cutflowCanWrite={Boolean(actor && ['ADMIN', 'OPERATOR', 'USER'].includes(actor.role))}
      /></Suspense> : null}
      {view === 'admin' ? <Suspense fallback={<PageLoading />}><AdminCenterView system={system} actor={actor} section={adminSection} onSectionChange={(section) => navigate('admin', null, false, section)} onKlingChanged={refresh} /></Suspense> : null}
      {view === 'settings' ? <Suspense fallback={<PageLoading />}><SettingsView
        system={system}
        actorId={actorId}
        canDeleteSubjects={actor?.role === 'ADMIN'}
        canEditCatalog={Boolean(actor)}
        onLogout={() => void signOut()}
        browserNotificationsEnabled={browserNotificationsEnabled}
        browserNotificationPermission={notificationPermission}
        onEnableBrowserNotifications={enableBrowserNotifications}
        onDisableBrowserNotifications={disableBrowserNotifications}
      /></Suspense> : null}
    </>}
  </AppShell>
}

export default App
