import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Bell,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  Clapperboard,
  Clock3,
  Copy,
  Download,
  Eye,
  EyeOff,
  FileImage,
  Film,
  Globe2,
  HelpCircle,
  KeyRound,
  LayoutDashboard,
  ListVideo,
  LoaderCircle,
  LogIn,
  LogOut,
  LockKeyhole,
  MoreHorizontal,
  Package,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Search,
  Settings,
  ShieldCheck,
  UploadCloud,
  UserRound,
  WandSparkles,
  ThumbsDown,
  ThumbsUp,
  X,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { createPortal } from 'react-dom'
import {
  ApiError,
  analyzeTask,
  changePassword,
  confirmTask,
  createAdminUser,
  createTask,
  deactivateAdminUser,
  fetchArtifactObjectUrl,
  fetchAssetFile,
  fetchAssetObjectUrl,
  getSystemStatus,
  getCurrentUser,
  getTaskPage,
  getTask,
  restoreOutput,
  reuseTask,
  saveArtifact,
  setApiUserId,
  setCsrfCookieName,
  uploadStoryboard,
  getAdminCredentials,
  getAdminUsers,
  getLibTVAccountStatus,
  getKlingStatus,
  getOperations,
  getPersonalPromptAutoConfirmation,
  loginKling,
  logoutKling,
  startLibTVLogin,
  updateAdminCredentials,
  switchLibTVAccount,
  refreshKlingCapabilities,
  resetAdminUserPassword,
  login,
  logout,
  runPromptAssistant,
  saveTaskPrompts,
  setPromptAutoConfirmation,
  setPersonalPromptAutoConfirmation,
  setVariantFeedback,
} from './api'
import { mapWithConcurrency } from './concurrency'
import type { AdminCredentialsStatus, AdminUser, AuthUser, FeedbackValue, KlingStatus, LibTVAccountStatus, StatusTone, SystemStatus, Task, Variant, VariantKind } from './types'
import { GenerationFeedbackPanel } from './GenerationFeedback'
import { OperationsPanel } from './OperationsPanel'
import { IMAGE_FILE_ACCEPT, isSupportedImageFile } from './imageFiles'
import { formatRiskFlags } from './riskLabels'
import { formatDurationSeconds, formatElapsed, parseTaskTimestamp } from './taskTiming'
import { createUuid } from './uuid'
import {
  readBrowserNotificationPreference,
  shouldCloseTaskNotification,
  taskNotificationForTransition,
  writeBrowserNotificationPreference,
} from './browserNotifications'

type View = 'make' | 'records' | 'admin' | 'settings'
type AdminSection = 'overview' | 'accounts' | 'providers' | 'security'
type GenerationProvider = 'libtv' | 'kling'
type OutputVariantSelection = 'stable' | 'dynamic' | 'both'
type UploadBucket = 'storyboard' | 'product'
type Material = { id: string; file: File }
type RemixSeed = { id: string; storyboards: File[]; products: File[]; requirement?: string }
type RecordFilter = 'all' | 'attention' | 'active' | 'partial' | 'done' | 'failed' | 'cancelled'

const UPLOAD_CONCURRENCY = 4
const OUTPUT_VARIANT_STORAGE_KEY = 'default-output-variants'
const DISMISSED_ATTENTION_STORAGE_KEY = 'dismissed-home-attention'
const DISMISSED_ATTENTION_ITEMS_STORAGE_KEY = 'dismissed-home-attention-items'

function browserNotificationPermission(): NotificationPermission | 'unsupported' {
  return 'Notification' in window ? Notification.permission : 'unsupported'
}

function readOutputVariantSelection(): OutputVariantSelection {
  const stored = localStorage.getItem(OUTPUT_VARIANT_STORAGE_KEY)
  return stored === 'stable' || stored === 'dynamic' || stored === 'both' ? stored : 'both'
}

function selectedVariantKinds(selection: OutputVariantSelection): VariantKind[] {
  if (selection === 'stable') return ['STABLE']
  if (selection === 'dynamic') return ['DYNAMIC']
  return ['STABLE', 'DYNAMIC']
}

function taskPrompt(task: Task, kind: VariantKind): string {
  return task.variants.find((variant) => variant.kind === kind)?.promptText
    ?? task.variants[0]?.promptText
    ?? ''
}

function readAppLocation(): { view: View; detailId: string | null; adminSection: AdminSection } {
  const params = new URLSearchParams(window.location.search)
  const requestedView = params.get('view')
  const view: View = requestedView === 'records' || requestedView === 'admin' || requestedView === 'settings' ? requestedView : 'make'
  const requestedAdminSection = params.get('section')
  const adminSection: AdminSection = requestedAdminSection === 'accounts' || requestedAdminSection === 'providers' || requestedAdminSection === 'security'
    ? requestedAdminSection
    : 'overview'
  return { view, detailId: view === 'make' ? params.get('task') : null, adminSection }
}

const ACTIVE_PHASES = new Set(['DRAFT', 'ANALYZING', 'PREPARING', 'WAITING_FOR_SEAL', 'QUEUED', 'GENERATING', 'DOWNLOADING', 'VALIDATING'])
const RESULT_PHASES = new Set(['DELIVERABLE', 'PARTIALLY_DELIVERABLE'])
const COMPLETED_PHASES = new Set(['DELIVERABLE'])
const TERMINAL_PHASES = new Set(['DELIVERABLE', 'PARTIALLY_DELIVERABLE', 'ACTION_REQUIRED', 'CANCELLED'])

function validateCompatibleBaseUrl(value: string): string {
  const normalized = value.trim()
  if (!normalized) return ''
  try {
    const url = new URL(normalized)
    const loopback = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)
    if (url.protocol !== 'https:' && !(url.protocol === 'http:' && loopback)) return '请使用 HTTPS；仅本机地址允许 HTTP。'
    if (url.username || url.password || url.search || url.hash) return '地址不能包含账号密码、查询参数或片段。'
  } catch { return '请输入完整地址，例如 https://gateway.example.com/v1。' }
  return ''
}
const FAILED_PHASES = new Set(['ACTION_REQUIRED'])
const DEFAULT_ANALYSIS_MODEL = 'gpt-5.6-terra'
const LEGACY_ANALYSIS_MODEL = 'gpt-5.6-sol'

function readDefaultAnalysisModel(configuredModel?: string): string {
  const stored = localStorage.getItem('default-model')?.trim()
  const configured = configuredModel?.trim() || DEFAULT_ANALYSIS_MODEL
  return !stored || stored === LEGACY_ANALYSIS_MODEL ? configured : stored
}
const ANALYSIS_FAILURE_CODES = new Set([
  'ANALYSIS_TIMEOUT',
  'ANALYSIS_CANCELLED',
  'ANALYSIS_PROVIDER_FAILED',
  'ANALYSIS_STALE_RECOVERED',
  'ANALYSIS_SCHEMA_INVALID',
])

const analysisStageLabels: Record<string, string> = {
  QUEUED: '等待后台分析',
  PREPARING_IMAGES: '正在准备图片',
  PROVIDER_RUNNING: '大模型正在分析素材',
  VALIDATING: '正在校验 A/B 方案',
}

const statusMeta: Record<string, { label: string; tone: StatusTone }> = {
  DRAFT: { label: '正在上传素材', tone: 'neutral' },
  ANALYZING: { label: '正在分析图片', tone: 'active' },
  AWAITING_CONFIRMATION: { label: '等待确认方案', tone: 'warning' },
  PREPARING: { label: '正在准备生成', tone: 'active' },
  QUEUED: { label: '等待生成', tone: 'active' },
  GENERATING: { label: '正在生成视频', tone: 'active' },
  PARTIALLY_DELIVERABLE: { label: '部分完成', tone: 'warning' },
  DELIVERABLE: { label: '已完成', tone: 'success' },
  ACTION_REQUIRED: { label: '任务需要处理', tone: 'danger' },
  CANCELLED: { label: '已取消', tone: 'neutral' },
  SUCCEEDED: { label: '已完成', tone: 'success' },
  PARTIAL: { label: '部分完成', tone: 'warning' },
  RUNNING: { label: '正在生成视频', tone: 'active' },
  PENDING: { label: '等待生成', tone: 'neutral' },
  FAILED: { label: '生成失败', tone: 'danger' },
  UNKNOWN: { label: '状态待确认', tone: 'warning' },
  READY: { label: '可下载', tone: 'success' },
}

const phaseProgress: Record<string, number> = {
  DRAFT: 8,
  ANALYZING: 28,
  AWAITING_CONFIRMATION: 45,
  PREPARING: 55,
  QUEUED: 64,
  GENERATING: 78,
  PARTIALLY_DELIVERABLE: 92,
  DELIVERABLE: 100,
  ACTION_REQUIRED: 100,
  CANCELLED: 100,
}

const outputVariantMeta: Record<OutputVariantSelection, { title: string; description: string }> = {
  stable: { title: '一版 · A 稳定展示', description: '只生成稳定展示方案和 1 条视频' },
  dynamic: { title: '一版 · B 动态广告', description: '只生成动态广告方案和 1 条视频' },
  both: { title: '两版 · A + B', description: '生成两套方案和 2 条视频' },
}

function formatTime(value: string) {
  return new Date(parseTaskTimestamp(value)).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

function TaskElapsed({ task }: { task: Pick<Task, 'phase' | 'createdAt' | 'updatedAt'> }) {
  const isTerminal = TERMINAL_PHASES.has(task.phase)
  const [now, setNow] = useState(Date.now)
  useEffect(() => {
    if (isTerminal) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [isTerminal])
  return <>{formatElapsed(task.createdAt, isTerminal ? task.updatedAt : now)}</>
}

type TaskTimingStage = NonNullable<Task['timing']>['stages'][number]

const TASK_TIMING_STAGE_META: Array<{
  key: TaskTimingStage['key']
  category: 'system' | 'user'
}> = [
  { key: 'SOURCE_UPLOAD', category: 'system' },
  { key: 'ANALYSIS', category: 'system' },
  { key: 'CONFIRMATION', category: 'user' },
  { key: 'MATERIALIZATION', category: 'system' },
  { key: 'GENERATION', category: 'system' },
  { key: 'DOWNLOAD', category: 'system' },
]

function taskTimingStageLabel(key: TaskTimingStage['key'], provider: string): string {
  if (key === 'SOURCE_UPLOAD') return '素材上传'
  if (key === 'ANALYSIS') return '内容分析'
  if (key === 'CONFIRMATION') return '方案确认'
  if (key === 'MATERIALIZATION') return provider === 'kling' ? '上传至可灵' : '上传至 LibTV'
  if (key === 'GENERATION') return provider === 'kling' ? '可灵生成视频' : 'LibTV 生成视频'
  return '成品下载'
}

function taskTimingStageShortLabel(key: TaskTimingStage['key']): string {
  if (key === 'SOURCE_UPLOAD') return '素材'
  if (key === 'ANALYSIS') return '分析'
  if (key === 'CONFIRMATION') return '确认'
  if (key === 'MATERIALIZATION') return '上传'
  if (key === 'GENERATION') return '生成'
  return '下载'
}

function formatCompactDurationSeconds(value: number): string {
  const seconds = Math.max(0, Math.floor(value))
  if (seconds < 60) return `${seconds}秒`
  if (seconds < 3600) {
    const minutes = Math.floor(seconds / 60)
    const remainder = seconds % 60
    return remainder ? `${minutes}分${remainder}秒` : `${minutes}分钟`
  }
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  return minutes ? `${hours}时${minutes}分` : `${hours}小时`
}

function stageElapsedSeconds(stage: TaskTimingStage, now: number): number | null {
  const recorded = stage.durationSeconds ?? 0
  if (stage.status !== 'ACTIVE' || !stage.activeStartedAt) {
    return stage.durationSeconds
  }
  const live = Math.max(0, (now - parseTaskTimestamp(stage.activeStartedAt)) / 1000)
  return stage.key === 'ANALYSIS' ? recorded + live : live
}

function TaskTimingTimeline({ task }: { task: Task }) {
  const stagesByKey = new Map((task.timing?.stages ?? []).map((stage) => [stage.key, stage]))
  const hasActiveStage = task.timing?.stages.some((stage) => stage.status === 'ACTIVE') ?? false
  const [now, setNow] = useState(Date.now)
  useEffect(() => {
    if (!hasActiveStage) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [hasActiveStage])

  const stages = TASK_TIMING_STAGE_META.map((meta) => ({
    ...meta,
    stage: stagesByKey.get(meta.key) ?? {
      key: meta.key,
      status: 'PENDING' as const,
      durationSeconds: null,
      activeStartedAt: null,
      attemptCount: null,
    },
  }))
  const activeStage = stages.find(({ stage }) => stage.status === 'ACTIVE')
  const sourceUploadSeconds = stagesByKey.get('SOURCE_UPLOAD')?.durationSeconds ?? 0
  const taskEnd = TERMINAL_PHASES.has(task.phase) ? parseTaskTimestamp(task.updatedAt) : now
  const totalSeconds = sourceUploadSeconds + Math.max(0, (taskEnd - parseTaskTimestamp(task.createdAt)) / 1000)
  const systemSeconds = stages.reduce((total, item) => {
    if (item.category !== 'system') return total
    return total + (stageElapsedSeconds(item.stage, now) ?? 0)
  }, 0)
  const confirmationStage = stagesByKey.get('CONFIRMATION')
  const confirmationSeconds = confirmationStage ? stageElapsedSeconds(confirmationStage, now) ?? 0 : 0

  return <section className="task-timing" aria-labelledby="task-timing-title">
    <header className="task-timing-header">
      <div>
        <span>{activeStage ? '当前阶段' : COMPLETED_PHASES.has(task.phase) ? '任务已完成' : task.phase === 'PARTIALLY_DELIVERABLE' ? '部分结果已就绪' : '执行状态'}</span>
        <h3 id="task-timing-title">
          {activeStage ? taskTimingStageLabel(activeStage.key, task.generationProvider) : taskStatus(task).label}
        </h3>
        {activeStage ? <p aria-live="polite">已进行 {formatDurationSeconds(stageElapsedSeconds(activeStage.stage, now) ?? 0)}</p> : null}
      </div>
      <dl className="task-timing-summary" aria-label="任务耗时汇总">
        <div><dt>系统处理</dt><dd>{systemSeconds > 0 ? formatDurationSeconds(systemSeconds) : '暂无记录'}</dd></div>
        <div><dt>等待确认</dt><dd>{confirmationSeconds > 0 ? formatDurationSeconds(confirmationSeconds) : '0 秒'}</dd></div>
        <div><dt>总耗时</dt><dd>{formatDurationSeconds(totalSeconds)}</dd></div>
      </dl>
    </header>
    <ol className="task-timing-stages">
      {stages.map(({ key, category, stage }, index) => {
        const elapsed = stageElapsedSeconds(stage, now)
        const statusText = stage.status === 'ACTIVE'
          ? formatCompactDurationSeconds(elapsed ?? 0)
          : stage.status === 'COMPLETED'
            ? elapsed === null ? '已完成' : formatCompactDurationSeconds(elapsed)
            : stage.status === 'FAILED' ? '未完成' : '待执行'
        const fullLabel = taskTimingStageLabel(key, task.generationProvider)
        return <li key={key} className={`task-timing-stage is-${stage.status.toLowerCase()}`} aria-label={`${fullLabel}，${category === 'user' ? '用户等待' : '系统处理'}，${statusText}`} aria-current={stage.status === 'ACTIVE' ? 'step' : undefined}>
          <span className="task-timing-marker" aria-hidden="true">
            {stage.status === 'COMPLETED' ? <Check size={15} /> : stage.status === 'ACTIVE' ? <LoaderCircle className="spin" size={15} /> : stage.status === 'FAILED' ? <AlertTriangle size={15} /> : index + 1}
          </span>
          <span className="task-timing-copy">
            <strong><span className="task-timing-label-full">{fullLabel}</span><span className="task-timing-label-short">{taskTimingStageShortLabel(key)}</span></strong>
            <small>{category === 'user' ? '用户等待' : '系统处理'}{stage.attemptCount && stage.attemptCount > 1 ? ` · 共 ${stage.attemptCount} 次` : ''}</small>
          </span>
          <span className="task-timing-duration">{statusText}</span>
        </li>
      })}
    </ol>
  </section>
}

function StatusBadge({ value }: { value: string | null }) {
  if (!value) return <span className="status status--neutral"><span />状态待确认</span>
  const meta = statusMeta[value] ?? { label: value, tone: 'neutral' as const }
  return <span className={`status status--${meta.tone}`}><span />{meta.label}</span>
}

function isAnalysisFailure(task: Task): boolean {
  return task.phase === 'ACTION_REQUIRED' && ANALYSIS_FAILURE_CODES.has(task.phaseReasonCode ?? '')
}

function taskStatus(task: Task): { label: string; tone: StatusTone } {
  if (!isAnalysisFailure(task)) return statusMeta[task.phase] ?? { label: task.phase, tone: 'neutral' }
  const labels: Record<string, string> = {
    ANALYSIS_TIMEOUT: '方案分析超时',
    ANALYSIS_CANCELLED: '方案分析中断',
    ANALYSIS_PROVIDER_FAILED: '分析服务异常',
    ANALYSIS_STALE_RECOVERED: '方案分析待重试',
    ANALYSIS_SCHEMA_INVALID: '方案数据异常',
  }
  return { label: labels[task.phaseReasonCode ?? ''] ?? '方案分析未完成', tone: 'danger' }
}

function taskFailureMessage(task: Task): string {
  const messages: Record<string, string> = {
    ANALYSIS_TIMEOUT: '素材较多或分析服务耗时较长，已达到本次按素材数量计算的等待上限。',
    ANALYSIS_CANCELLED: '上一次后台分析意外中断，素材仍然保留。',
    ANALYSIS_PROVIDER_FAILED: '分析服务暂时没有返回有效结果，素材仍然保留。',
    ANALYSIS_STALE_RECOVERED: '系统检测到后台分析长时间没有更新，已停止等待旧任务。',
    ANALYSIS_SCHEMA_INVALID: '分析结果不完整，无法生成可确认的 A/B 方案。',
  }
  return messages[task.phaseReasonCode ?? ''] ?? '任务遇到问题，需要查看技术信息后处理。'
}

function TaskStatusBadge({ task }: { task: Task }) {
  const meta = taskStatus(task)
  return <span className={`status status--${meta.tone}`}><span />{meta.label}</span>
}

function klingStatusMessage(status: string | undefined, fallback?: string | null) {
  const messages: Record<string, string> = {
    KLING_CLI_NOT_INSTALLED: '可灵官方 CLI 未安装',
    KLING_CLI_NOT_AUTHENTICATED: '可灵账号未登录，请运行 kling login',
    KLING_CAPABILITY_FETCH_FAILED: '可灵能力发现失败',
    KLING_CAPABILITY_UNSUPPORTED: '可灵官方 CLI Provider 当前未启用',
    KLING_CLI_READY: '可灵官方 CLI 已就绪',
  }
  return (status && messages[status]) || fallback || '可灵官方 CLI 当前不可用'
}

function useDismiss(open: boolean, onClose: () => void, containerRef?: React.RefObject<HTMLElement | null>) {
  const onCloseRef = useRef(onClose)
  useEffect(() => { onCloseRef.current = onClose }, [onClose])
  useEffect(() => {
    if (!open) return
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const focusableSelector = 'button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])'
    const close = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCloseRef.current()
      if (event.key !== 'Tab' || !containerRef?.current) return
      const focusable = Array.from(containerRef.current.querySelectorAll<HTMLElement>(focusableSelector))
      if (!focusable.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }
    document.body.classList.add('overlay-open')
    window.addEventListener('keydown', close)
    containerRef?.current?.querySelector<HTMLElement>(focusableSelector)?.focus()
    return () => {
      document.body.classList.remove('overlay-open')
      window.removeEventListener('keydown', close)
      previousFocus?.focus()
    }
  }, [containerRef, open])
}

function AuthenticatedImage({ src, alt, eager = false }: { src: string; alt: string; eager?: boolean }) {
  const [objectUrl, setObjectUrl] = useState('')
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    let active = true
    let loadedUrl = ''
    void fetchAssetObjectUrl(src).then((url) => {
      loadedUrl = url
      if (active) setObjectUrl(url)
    }).catch(() => { if (active) setFailed(true) })
    return () => {
      active = false
      if (loadedUrl) URL.revokeObjectURL(loadedUrl)
    }
  }, [src])
  if (failed) return <span className="image-fallback"><FileImage size={20} /><small>图片不可用</small></span>
  return objectUrl ? <img src={objectUrl} alt={alt} loading={eager ? 'eager' : 'lazy'} /> : <span className="image-skeleton" aria-label="图片加载中" />
}

function LocalImage({ file, alt }: { file: File; alt: string }) {
  const [preview, setPreview] = useState<{ file: File; src: string } | null>(null)
  useEffect(() => {
    let active = true
    const src = URL.createObjectURL(file)
    queueMicrotask(() => {
      if (active) setPreview({ file, src })
    })
    return () => {
      active = false
      URL.revokeObjectURL(src)
    }
  }, [file])
  return preview?.file === file
    ? <img src={preview.src} alt={alt} draggable={false} />
    : <span className="image-skeleton" aria-label="图片加载中" />
}

function ImagePreview({ file, label, onClose }: { file: File; label: string; onClose: () => void }) {
  const dialogRef = useRef<HTMLElement>(null)
  useDismiss(true, onClose, dialogRef)
  return createPortal(<div className="modal-backdrop image-preview-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
    <section ref={dialogRef} className="image-preview-modal" role="dialog" aria-modal="true" aria-labelledby="image-preview-title">
      <h2 id="image-preview-title" className="sr-only">{label}：{file.name}</h2>
      <div className="image-preview-stage">
        <LocalImage file={file} alt={`${label}大图：${file.name}`} />
      </div>
      <button type="button" className="icon-button image-preview-close" onClick={onClose} aria-label="关闭图片预览" title="关闭预览"><X size={19} /></button>
    </section>
  </div>, document.body)
}

function TaskThumb({ task, large = false }: { task: Task; large?: boolean }) {
  const asset = [...task.assets].sort((a, b) => a.order - b.order)[0]
  return <span className={`task-thumb ${large ? 'task-thumb--large' : ''}`}>
    {asset ? <AuthenticatedImage src={asset.thumbnailUrl} alt={`${task.title} 产品图`} eager={large} /> : <Package size={20} />}
  </span>
}

function ProductLogo() {
  return <span className="brand-lockup"><span className="brand-mark"><Clapperboard size={19} /></span><span><strong>衣影工坊</strong><small>LibTV 视频生产</small></span></span>
}

function loginErrorMessage(cause: unknown): string {
  if (!(cause instanceof ApiError)) return '无法连接生产服务，请检查网络后重试'
  if (cause.status === 401) return '账号或密码不正确，请重新输入'
  if (cause.status === 408) return '生产服务响应超时，请稍后重试'
  if (cause.status === 409) return '当前服务尚未启用团队账号登录'
  if (cause.status >= 500) return '生产服务暂时不可用，请稍后重试'
  return cause.message || '登录失败，请稍后重试'
}

function LoginScreen({ onAuthenticated }: { onAuthenticated: () => Promise<void> }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    document.body.classList.add('login-open')
    return () => document.body.classList.remove('login-open')
  }, [])
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await login(username.trim(), password)
      await onAuthenticated()
    } catch (cause) {
      setError(loginErrorMessage(cause))
    } finally { setBusy(false) }
  }
  return <main className="login-view">
    <section className="login-shell" aria-label="衣影工坊账号登录">
      <aside className="login-brand-panel">
        <ProductLogo />
        <div className="login-brand-copy">
          <span>LIBTV PRODUCTION</span>
          <h1>衣影工坊</h1>
          <p>视频生产管理系统</p>
        </div>
        <div className="login-environment"><span aria-hidden="true" />团队生产环境</div>
      </aside>
      <form className="login-panel" onSubmit={(event) => void submit(event)} aria-busy={busy}>
        <div className="login-mobile-brand"><ProductLogo /></div>
        <div className="login-heading"><span>账号登录</span><h2>欢迎回来</h2><p>使用管理员分配的生产账号进入工作台。</p></div>
        <div className="login-field">
          <label htmlFor="login-username">账号</label>
          <span className="login-input-wrap"><UserRound size={18} aria-hidden="true" /><input id="login-username" name="username" value={username} onChange={(event) => { setUsername(event.target.value); setError('') }} autoComplete="username" autoCapitalize="none" spellCheck={false} disabled={busy} aria-invalid={Boolean(error)} aria-describedby={error ? 'login-error' : undefined} autoFocus required /></span>
        </div>
        <div className="login-field">
          <label htmlFor="login-password">密码</label>
          <span className="login-input-wrap"><KeyRound size={18} aria-hidden="true" /><input id="login-password" name="password" type={showPassword ? 'text' : 'password'} value={password} onChange={(event) => { setPassword(event.target.value); setError('') }} autoComplete="current-password" disabled={busy} aria-invalid={Boolean(error)} aria-describedby={error ? 'login-error' : undefined} required /><button type="button" className="login-password-toggle" onClick={() => setShowPassword((current) => !current)} disabled={busy} aria-label={showPassword ? '隐藏密码' : '显示密码'} title={showPassword ? '隐藏密码' : '显示密码'}>{showPassword ? <EyeOff size={18} /> : <Eye size={18} />}</button></span>
        </div>
        <div className="login-feedback" aria-live="polite">
          {error ? <div id="login-error" className="inline-alert inline-alert--danger login-error" role="alert"><AlertTriangle size={17} />{error}</div> : null}
        </div>
        <button className="primary-button primary-button--large" type="submit" disabled={busy || !username.trim() || !password}>{busy ? <LoaderCircle className="spin" size={18} /> : <LogIn size={18} />}{busy ? '正在验证账号' : '登录'}</button>
        <p className="login-security-note"><ShieldCheck size={16} aria-hidden="true" />账号权限和操作记录由系统统一管理</p>
      </form>
    </section>
  </main>
}

const MATERIAL_DRAG_TYPE = 'application/x-libtv-material'

function MaterialCard({ material, bucket, index, onRemove, onDropAt, onPreview }: {
  material: Material
  bucket: UploadBucket
  index: number
  onRemove: () => void
  onDropAt: (event: React.DragEvent, target: number) => void
  onPreview: () => void
}) {
  const dragStartedRef = useRef(false)
  return <article
    className="material-card"
    title={material.file.name}
    draggable
    onDragStart={(event) => {
      dragStartedRef.current = true
      event.dataTransfer.effectAllowed = 'move'
      event.dataTransfer.setData(MATERIAL_DRAG_TYPE, material.id)
      event.dataTransfer.setData('text/material-bucket', bucket)
      event.currentTarget.classList.add('is-dragging')
    }}
    onDragEnd={(event) => {
      event.currentTarget.classList.remove('is-dragging')
      window.setTimeout(() => { dragStartedRef.current = false }, 0)
    }}
    onDragOver={(event) => {
      event.preventDefault()
      event.dataTransfer.dropEffect = event.dataTransfer.types.includes(MATERIAL_DRAG_TYPE) ? 'move' : 'copy'
    }}
    onDrop={(event) => onDropAt(event, index)}
  >
    <div className="material-preview">
      <div
        role="button"
        tabIndex={0}
        className="material-preview-trigger"
        onClick={() => {
          if (!dragStartedRef.current) onPreview()
        }}
        onKeyDown={(event) => {
          if (event.key !== 'Enter' && event.key !== ' ') return
          event.preventDefault()
          if (!dragStartedRef.current) onPreview()
        }}
        aria-label={`查看图片 ${index + 1} 大图`}
        title="点击查看大图，长按拖拽排序"
      >
        <LocalImage file={material.file} alt={material.file.name} />
      </div>
      <span className="order-index">{index + 1}</span>
      <button
        type="button"
        className="material-remove"
        onClick={(event) => {
          event.stopPropagation()
          onRemove()
        }}
        onPointerDown={(event) => event.stopPropagation()}
        aria-label={`删除图片 ${index + 1}`}
        title="删除图片"
      >
        <X size={14} strokeWidth={2.25} />
      </button>
    </div>
  </article>
}

function ProductionComposer({ seed, onCreated, system }: {
  seed: RemixSeed | null
  onCreated: (task: Task, open?: boolean) => void
  system: SystemStatus | null
}) {
  const [storyboards, setStoryboards] = useState<Material[]>(() => seed?.storyboards.map((file) => ({ id: createUuid(), file })) ?? [])
  const [products, setProducts] = useState<Material[]>(() => seed?.products.map((file) => ({ id: createUuid(), file })) ?? [])
  const [analysisModel] = useState(() => readDefaultAnalysisModel(system?.openaiModel))
  const [generationProvider] = useState<GenerationProvider>(() => (localStorage.getItem('generation-provider') as GenerationProvider | null) ?? 'libtv')
  const [outputVariants, setOutputVariants] = useState<OutputVariantSelection>(readOutputVariantSelection)
  const [requirement, setRequirement] = useState(seed?.requirement ?? '')
  const [busy, setBusy] = useState(false)
  const [stage, setStage] = useState('正在上传素材')
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [preview, setPreview] = useState<{ file: File; label: string } | null>(null)
  const storyboardInputRef = useRef<HTMLInputElement>(null)
  const productInputRef = useRef<HTMLInputElement>(null)
  const providerAvailable = generationProvider === 'libtv' || Boolean(system?.kling.available && system.kling.authenticated)
  const storyboardSupported = generationProvider !== 'kling'
    || storyboards.length <= (system?.kling.imageInputLimit ?? 0)
    || system?.kling.fallbackMode === 'first_last_frame'
  const addFiles = (bucket: UploadBucket, files: File[]) => {
    const images = files.filter(isSupportedImageFile)
    const rejectedCount = files.length - images.length
    const limit = bucket === 'storyboard' ? 7 : 5
    const current = bucket === 'storyboard' ? storyboards : products
    const accepted = images.slice(0, Math.max(0, limit - current.length)).map((file) => ({ id: createUuid(), file }))
    const notices: string[] = []
    if (rejectedCount) notices.push(`${rejectedCount} 个文件不是支持的 JPG、PNG 或 WEBP 图片`)
    if (images.length !== accepted.length) notices.push(bucket === 'storyboard' ? '分镜图最多添加 7 张，超出部分未添加' : '产品图最多添加 5 张，超出部分未添加')
    setNotice(notices.join('；'))
    if (bucket === 'storyboard') setStoryboards((items) => [...items, ...accepted])
    else setProducts((items) => [...items, ...accepted])
  }
  const setBucket = (bucket: UploadBucket, updater: (items: Material[]) => Material[]) => bucket === 'storyboard' ? setStoryboards(updater) : setProducts(updater)
  const dropAt = (event: React.DragEvent, targetBucket: UploadBucket, target: number) => {
    event.preventDefault()
    event.stopPropagation()
    const id = event.dataTransfer.getData(MATERIAL_DRAG_TYPE)
    const sourceBucket = event.dataTransfer.getData('text/material-bucket') as UploadBucket
    if (!id || (sourceBucket !== 'storyboard' && sourceBucket !== 'product')) return
    if (sourceBucket !== targetBucket) return
    const sourceItems = sourceBucket === 'storyboard' ? storyboards : products
    const item = sourceItems.find((value) => value.id === id)
    if (!item) return
    const sourceIndex = sourceItems.findIndex((value) => value.id === id)
    if (sourceIndex === target) return
    setBucket(targetBucket, (current) => {
      const next = [...current]
      const currentSourceIndex = next.findIndex((value) => value.id === id)
      if (currentSourceIndex < 0) return current
      const [moved] = next.splice(currentSourceIndex, 1)
      next.splice(Math.min(target, next.length), 0, moved)
      return next
    })
  }
  const remove = (bucket: UploadBucket, id: string) => setBucket(bucket, (items) => items.filter((item) => item.id !== id))
  const handleDrop = (event: React.DragEvent, bucket: UploadBucket, target: number) => {
    if (event.dataTransfer.types.includes(MATERIAL_DRAG_TYPE)) {
      dropAt(event, bucket, target)
      return
    }
    if (!event.dataTransfer.files.length) return
    event.preventDefault()
    event.stopPropagation()
    addFiles(bucket, Array.from(event.dataTransfer.files))
  }
  const submit = async () => {
    if (!storyboards.length || !providerAvailable || !storyboardSupported) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const allMaterials = [...storyboards, ...products]
      const uploadStartedAt = performance.now()
      let completedUploads = 0
      const uploads = await mapWithConcurrency(
        allMaterials,
        UPLOAD_CONCURRENCY,
        async (material) => {
          const uploaded = await uploadStoryboard(material.file)
          completedUploads += 1
          setStage(`正在上传图片 ${completedUploads}/${allMaterials.length}`)
          setProgress(Math.round((completedUploads / allMaterials.length) * 28))
          return uploaded
        },
      )
      setStage('正在分析图片')
      setProgress(36)
      const storyboardUploads = uploads.slice(0, storyboards.length)
      const productUploads = uploads.slice(storyboards.length)
      const sourceUploadDurationSeconds = (performance.now() - uploadStartedAt) / 1000
      const product = products[0] ?? storyboards[0]
      const baseName = product.file.name.replace(/\.[^.]+$/, '').trim().slice(0, 80) || '服装广告视频'
      const draft = await createTask(
        `${baseName} · ${formatTime(new Date().toISOString())}`,
        requirement.trim(),
        storyboardUploads,
        productUploads,
        { analysisModel: analysisModel.trim(), generationProvider, variants: selectedVariantKinds(outputVariants) },
        sourceUploadDurationSeconds,
      )
      onCreated({ ...draft, phase: 'ANALYZING' }, true)
      localStorage.removeItem('video-direction')
      localStorage.setItem('default-model', analysisModel.trim())
      localStorage.setItem('generation-provider', generationProvider)
      localStorage.setItem(OUTPUT_VARIANT_STORAGE_KEY, outputVariants)
      void analyzeTask(draft)
        .then(onCreated)
        .catch(async () => {
          try {
            onCreated(await getTask(draft.id))
          } catch { /* The global task poll remains the fallback. */ }
        })
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '素材提交失败，请检查图片后重试')
    } finally {
      setBusy(false)
      setProgress(0)
    }
  }

  return <section className="composer" aria-labelledby="composer-title">
    <div className="composer-head">
      <div><span className="section-kicker">新建视频</span><h2 id="composer-title">上传分镜图与产品参考图</h2><p>分镜图用于 {generationProvider === 'kling' ? '可灵官方 CLI' : 'LibTV'} 生成；产品图仅作为印花款式等细节的分析参考。</p></div>
      <span className="step-pill"><span>1</span> 上传素材</span>
    </div>
    {busy ? <div className="analysis-state" role="status">
      <span className="analysis-icon"><LoaderCircle className="spin" size={25} /></span>
      <div><strong>{stage}</strong><span>上传后自动分析素材并生成待确认方案，确认前不会生成视频</span></div>
      <span className="analysis-number">{progress}%</span>
      <div className="progress-track"><span style={{ width: `${progress}%` }} /></div>
    </div> : <>
      <div className="upload-panels">
        {([['storyboard', '分镜图', '至少 1 张，最多 7 张', storyboardInputRef, storyboards, 7], ['product', '产品图', '可不上传，最多 5 张', productInputRef, products, 5]] as const).map(([bucket, title, hint, ref, items, limit]) => <section className={`upload-panel upload-panel--${bucket}${items.length ? ' upload-panel--has-items' : ''}`} key={bucket} onDragOver={(event) => {
          event.preventDefault()
          event.dataTransfer.dropEffect = event.dataTransfer.types.includes(MATERIAL_DRAG_TYPE) ? 'move' : 'copy'
        }} onDrop={(event) => handleDrop(event, bucket, items.length)}>
          <input ref={ref} hidden type="file" multiple accept={IMAGE_FILE_ACCEPT} onChange={(event) => { addFiles(bucket, Array.from(event.target.files ?? [])); event.currentTarget.value = '' }} />
          <div className="upload-panel-head"><div><h2>{title}</h2><small>{hint}</small></div><span>{items.length}/{limit}</span></div>
          <button type="button" className="upload-zone upload-zone--compact" onClick={() => ref.current?.click()}><span className="upload-icon"><UploadCloud size={22} /></span><span><strong>{items.length ? `继续添加${title}` : `拖拽或点击上传${title}`}</strong><small>JPG、PNG、WEBP</small></span></button>
          {items.length ? <div className="materials-grid" aria-label={`${title}排序列表`}>{items.map((material, index) => <MaterialCard key={material.id} material={material} bucket={bucket} index={index} onRemove={() => remove(bucket, material.id)} onDropAt={(event, target) => handleDrop(event, bucket, target)} onPreview={() => setPreview({ file: material.file, label: `${title} ${index + 1}` })} />)}</div> : null}
        </section>)}
      </div>
      <div className="composer-options">
        <fieldset className="output-variant-field">
          <legend>输出版本 <small>决定方案与生成数量</small></legend>
          <div className="output-variant-control">
            {(Object.keys(outputVariantMeta) as OutputVariantSelection[]).map((value) => <label key={value} className={outputVariants === value ? 'is-selected' : ''}>
              <input type="radio" name="output-variants" value={value} checked={outputVariants === value} onChange={() => setOutputVariants(value)} />
              <span><strong>{outputVariantMeta[value].title}</strong><small>{outputVariantMeta[value].description}</small></span>
              {outputVariants === value ? <CheckCircle2 size={17} /> : null}
            </label>)}
          </div>
        </fieldset>
        <label className="requirement-field"><span>补充要求 <small>选填</small></span><textarea maxLength={4000} value={requirement} onChange={(event) => setRequirement(event.target.value)} placeholder="例如：重点展示背部印花，整体节奏简洁高级" /></label>
      </div>
      {!storyboards.length ? <div className="inline-alert"><CircleAlert size={17} /><span>请至少上传 1 张分镜图</span></div> : null}
      {notice ? <div className="inline-alert" role="status"><CircleAlert size={17} /><span>{notice}</span></div> : null}
      {error ? <div className="inline-alert inline-alert--danger" role="alert"><AlertTriangle size={17} /><span>{error}</span></div> : null}
      {!providerAvailable ? <div className="inline-alert inline-alert--danger" role="alert"><AlertTriangle size={16} />{klingStatusMessage(system?.kling.status, system?.kling.reason)}，请让管理员完成安装、登录和能力刷新。</div> : null}
      {providerAvailable && !storyboardSupported ? <div className="inline-alert inline-alert--danger" role="alert"><AlertTriangle size={16} />当前可灵 CLI 最多接收 {system?.kling.imageInputLimit ?? 0} 张分镜图，系统不会静默丢弃中间分镜。</div> : null}
      <div className="composer-submit-row"><span><LockKeyhole size={14} />分镜图将提交到 {generationProvider === 'kling' ? '可灵官方 CLI' : 'LibTV'}，产品图只参与图片分析</span><button className="primary-button primary-button--large" disabled={!storyboards.length || !analysisModel.trim() || !providerAvailable || !storyboardSupported} onClick={() => void submit()}><WandSparkles size={18} />开始分析素材<ArrowRight size={17} /></button></div>
    </>}
    {preview ? <ImagePreview file={preview.file} label={preview.label} onClose={() => setPreview(null)} /> : null}
  </section>
}

function SectionHeading({ title, count, action }: { title: string; count?: number; action?: React.ReactNode }) {
  return <div className="section-heading"><div><h2>{title}</h2>{typeof count === 'number' ? <span className="count-badge">{count}</span> : null}</div>{action}</div>
}

function ProcessingRow({ task, onOpen }: { task: Task; onOpen: () => void }) {
  const variants = task.variants.filter((item) => ['RUNNING', 'PENDING', 'UNKNOWN'].includes(item.generationStatus))
  return <button type="button" className="processing-row" onClick={onOpen} aria-label={`查看任务：${task.title}`}>
    <TaskThumb task={task} />
    <span className="processing-main"><span className="processing-main-head"><strong>{task.title}</strong><TaskStatusBadge task={task} /></span><span>{task.phase === 'GENERATING' ? `正在生成 ${variants.map((item) => item.kind === 'STABLE' ? 'A 稳定展示' : 'B 动态广告').join('、') || '视频'}` : taskStatus(task).label}</span></span>
    <span className="progress-cell"><span className="progress-summary"><span>进度</span><strong>{phaseProgress[task.phase] ?? 50}%</strong></span><span className="progress-track"><span style={{ width: `${phaseProgress[task.phase] ?? 50}%` }} /></span></span>
    <span className="elapsed"><Clock3 size={14} /><TaskElapsed task={task} /></span>
    <span className="processing-row-action">查看<ChevronRight size={16} /></span>
  </button>
}

function AttentionItem({ task, onOpen, onDismiss }: { task: Task; onOpen: () => void; onDismiss: () => void }) {
  const unknown = task.variants.some((variant) => variant.generationStatus === 'UNKNOWN')
  const isWaiting = task.phase === 'AWAITING_CONFIRMATION'
  const reason = task.phase === 'AWAITING_CONFIRMATION'
    ? '等待确认 A/B 动作方案'
    : unknown
      ? '暂时无法确认生成状态'
      : isAnalysisFailure(task)
        ? taskFailureMessage(task)
        : '视频生成遇到问题，需要处理'
  const action = task.phase === 'AWAITING_CONFIRMATION' ? '立即确认' : unknown ? '查询状态' : isAnalysisFailure(task) ? '重新分析' : '查看原因'
  return <article className="attention-item">
    <button type="button" className="attention-item-dismiss" onClick={onDismiss} aria-label={`关闭“${task.title}”的提醒`} title="关闭此提醒"><X size={16} /></button>
    <TaskThumb task={task} />
    <div><strong title={task.title}>{task.title}</strong><span>{reason} · {isWaiting ? '已等待' : '已用时'} <TaskElapsed task={task} /></span></div>
    <button type="button" className="primary-button" onClick={onOpen}>{action}<ArrowRight size={15} /></button>
  </article>
}

function VideoPreview({ artifactId, title, onClose }: { artifactId: string; title: string; onClose: () => void }) {
  const [url, setUrl] = useState('')
  const [error, setError] = useState('')
  const dialogRef = useRef<HTMLElement>(null)
  useDismiss(true, onClose, dialogRef)
  useEffect(() => {
    let active = true
    let loaded = ''
    void fetchArtifactObjectUrl(artifactId).then((value) => { loaded = value; if (active) setUrl(value) }).catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : '视频加载失败') })
    return () => { active = false; if (loaded) URL.revokeObjectURL(loaded) }
  }, [artifactId])
  return <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
    <section ref={dialogRef} className="video-modal" role="dialog" aria-modal="true" aria-labelledby="video-title">
      <header><div><span>视频预览</span><h2 id="video-title">{title}</h2></div><button className="icon-button" onClick={onClose} aria-label="关闭预览"><X size={19} /></button></header>
      <div className="video-stage">{url ? <video src={url} controls autoPlay playsInline /> : error ? <div className="video-error"><AlertTriangle size={24} /><strong>{error}</strong></div> : <LoaderCircle className="spin" size={28} />}</div>
    </section>
  </div>
}

function ResultCard({ task, variant, onPlay, onRemix, onOpen, onFeedbackChanged }: { task: Task; variant: Variant; onPlay: () => void; onRemix: () => void; onOpen: () => void; onFeedbackChanged: (task: Task) => void }) {
  const product = [...task.assets].sort((a, b) => a.order - b.order)[0]
  const ready = Boolean(variant.downloadArtifactId)
  const [feedbackBusy, setFeedbackBusy] = useState<FeedbackValue | null>(null)
  const [feedbackMessage, setFeedbackMessage] = useState('')
  const [animatedFeedback, setAnimatedFeedback] = useState<FeedbackValue | null>(null)
  const [feedbackPanel, setFeedbackPanel] = useState<FeedbackValue | null>(null)
  const feedbackAnchorRef = useRef<HTMLDivElement>(null)
  const submitFeedback = async (value: FeedbackValue) => {
    const nextValue = variant.feedback === value ? null : value
    setFeedbackBusy(value)
    setFeedbackMessage('')
    try {
      const changed = await setVariantFeedback(task.id, variant.id, nextValue)
      onFeedbackChanged(changed)
      setAnimatedFeedback(nextValue)
      setFeedbackPanel(nextValue)
      setFeedbackMessage(nextValue ? '已记录，可选择具体原因' : '已取消反馈')
      window.setTimeout(() => setAnimatedFeedback(null), 320)
    } catch (cause) {
      setFeedbackMessage(cause instanceof Error ? cause.message : '反馈提交失败，请重试')
    } finally {
      setFeedbackBusy(null)
    }
  }
  const saveFeedbackDetails = async (reasons: Variant['feedbackReasons'], comment: string | null) => {
    if (!feedbackPanel) return false
    setFeedbackBusy(feedbackPanel)
    setFeedbackMessage('')
    try {
      const changed = await setVariantFeedback(task.id, variant.id, feedbackPanel, { reasons, comment })
      onFeedbackChanged(changed)
      setFeedbackMessage('详细反馈已保存，将优化后续同类场景')
      return true
    } catch (cause) {
      setFeedbackMessage(cause instanceof Error ? cause.message : '详细反馈保存失败，请重试')
      return false
    } finally {
      setFeedbackBusy(null)
    }
  }
  return <article className={`result-card${feedbackPanel ? ' has-feedback-panel' : ''}`}>
    <button className="result-cover" onClick={ready ? onPlay : onOpen} aria-label={ready ? `播放 ${task.title}` : `查看 ${task.title}`}>
      {product ? <AuthenticatedImage src={product.thumbnailUrl} alt={`${task.title} 视频封面`} /> : <Film size={30} />}
      <span className={`variant-label ${variant.kind === 'STABLE' ? 'variant-label--a' : 'variant-label--b'}`}>{variant.kind === 'STABLE' ? 'A' : 'B'}</span>
      {ready ? <span className="play-button"><Play size={21} fill="currentColor" /></span> : <span className="result-state"><StatusBadge value={variant.generationStatus} /></span>}
      <span className="duration">10s</span>
    </button>
    <div className="result-body"><div><strong>{task.title}</strong><span>{variant.kind === 'STABLE' ? '稳定展示' : '动态广告'} · {formatTime(task.updatedAt)}</span></div>
    {ready ? <div ref={feedbackAnchorRef} className="result-feedback">
      <span className="feedback-copy" aria-live="polite">{feedbackMessage || (variant.feedback ? '感谢反馈，系统会持续学习' : '这个结果怎么样？')}</span>
      <span className="feedback-buttons">
        <button className={`feedback-button${variant.feedback === 'LIKE' ? ' is-selected is-positive' : ''}${animatedFeedback === 'LIKE' ? ' is-animating' : ''}`} disabled={feedbackBusy !== null} onClick={() => void submitFeedback('LIKE')} aria-label={variant.feedback === 'LIKE' ? '取消点赞' : '点赞此视频'} aria-pressed={variant.feedback === 'LIKE'} title="点赞"><span>{feedbackBusy === 'LIKE' ? <LoaderCircle className="spin" size={17} /> : <ThumbsUp size={18} />}</span></button>
        <button className={`feedback-button${variant.feedback === 'DISLIKE' ? ' is-selected is-negative' : ''}${animatedFeedback === 'DISLIKE' ? ' is-animating' : ''}`} disabled={feedbackBusy !== null} onClick={() => void submitFeedback('DISLIKE')} aria-label={variant.feedback === 'DISLIKE' ? '取消点踩' : '点踩此视频'} aria-pressed={variant.feedback === 'DISLIKE'} title="点踩"><span>{feedbackBusy === 'DISLIKE' ? <LoaderCircle className="spin" size={17} /> : <ThumbsDown size={18} />}</span></button>
      </span>
      {feedbackPanel ? <GenerationFeedbackPanel
        key={`${variant.id}-${feedbackPanel}`}
        value={feedbackPanel}
        initialReasons={variant.feedback === feedbackPanel ? (variant.feedbackReasons ?? []) : []}
        initialComment={variant.feedback === feedbackPanel ? variant.feedbackComment : null}
        anchorRef={feedbackAnchorRef}
        onClose={() => setFeedbackPanel(null)}
        onSave={saveFeedbackDetails}
      /> : null}
    </div> : null}
    <div className="result-actions">
      {ready ? <><button className="icon-button" onClick={onPlay} aria-label="播放视频" title="播放"><Play size={17} /></button><button className="icon-button" onClick={() => void saveArtifact(variant.downloadArtifactId!, `${task.title}-${variant.kind.toLowerCase()}.mp4`)} aria-label="下载视频" title="下载"><Download size={17} /></button><button className="icon-button" onClick={onOpen} aria-label="查看任务详情" title="查看任务详情"><Eye size={17} /></button></> : <button className="compact-button" onClick={onOpen}>查看状态</button>}
      <button className="remix-button" onClick={onRemix}><RotateCcw size={15} />同素材再制作</button>
    </div></div>
  </article>
}

type PlanShot = { action?: string; camera?: string; productDisplay?: string; shotFunction?: string; durationWeight?: number }
type VariantPlan = { continuityStrategy?: string; shots?: PlanShot[] }
type AnalysisResult = {
  garmentFacts?: { category?: string; mainColor?: string; secondaryColor?: string; print?: string; logo?: string; text?: string; fit?: string; frontSellingPoints?: string[]; backSellingPoints?: string[] }
  storyboardFacts?: Array<{ scene?: string; framing?: string; pose?: string; actionCandidates?: string[] }>
  consistencyObservations?: { summary?: string }
  riskFlags?: string[]
  stablePlan?: VariantPlan
  dynamicPlan?: VariantPlan
}

function PromptBlock({ variant, value, disabled, dirty, onChange }: { variant: Variant; value: string; disabled: boolean; dirty: boolean; onChange: (value: string) => void }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    await navigator.clipboard.writeText(value)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1600)
  }
  const inputId = `prompt-${variant.id}`
  return <div className="prompt-block"><div><label htmlFor={inputId}>最终提示词方案</label><span className={dirty ? 'unsaved-badge' : 'snapshot-tag'}>{dirty ? '确认时保存' : <><LockKeyhole size={13} />确认后锁定</>}</span></div><textarea id={inputId} value={value} disabled={disabled} maxLength={2000} onChange={(event) => onChange(event.target.value)} /><div className="prompt-block-actions"><span>{value.length} / 2000</span><button className="compact-button" disabled={!value} onClick={() => void copy()}>{copied ? <Check size={15} /> : <Copy size={15} />}{copied ? '已复制' : '复制'}</button></div></div>
}

type PromptRevisionMode = 'REGENERATE' | 'MODIFY'

function PromptRevision({
  kind,
  instruction,
  message,
  disabled,
  activeMode,
  onInstructionChange,
  onSubmit,
}: {
  kind: VariantKind
  instruction: string
  message: string
  disabled: boolean
  activeMode: PromptRevisionMode | null
  onInstructionChange: (value: string) => void
  onSubmit: (mode: PromptRevisionMode) => void
}) {
  const inputId = `prompt-revision-${kind.toLowerCase()}`
  return <section className="prompt-revision" aria-labelledby={`${inputId}-title`}>
    <div className="prompt-revision-heading">
      <div><WandSparkles size={16} /><span><strong id={`${inputId}-title`}>调整此方案</strong><small>重新生成，或用一句话精准修改</small></span></div>
      <button className="secondary-button" disabled={disabled} onClick={() => onSubmit('REGENERATE')}>{activeMode === 'REGENERATE' ? <LoaderCircle className="spin" size={16} /> : <RefreshCw size={16} />}重新生成</button>
    </div>
    <div className="prompt-revision-input">
      <label className="sr-only" htmlFor={inputId}>一句话修改当前方案</label>
      <input id={inputId} value={instruction} maxLength={2000} disabled={disabled} placeholder="例如：减少转身，增加服装正面特写" onChange={(event) => onInstructionChange(event.target.value)} onKeyDown={(event) => {
        if (event.key === 'Enter' && instruction.trim() && !disabled) onSubmit('MODIFY')
      }} />
      <button className="primary-button" disabled={disabled || !instruction.trim()} onClick={() => onSubmit('MODIFY')}>{activeMode === 'MODIFY' ? <LoaderCircle className="spin" size={16} /> : <WandSparkles size={16} />}一句话修改</button>
    </div>
    {message ? <p className="prompt-revision-message" role="status"><CheckCircle2 size={15} />{message}</p> : null}
  </section>
}

function PlanPanel({
  kind,
  plan,
  variant,
  risks,
  prompt,
  promptDirty,
  disabled,
  revisionInstruction,
  revisionMessage,
  activeRevisionMode,
  onPromptChange,
  onRevisionInstructionChange,
  onPromptRevision,
}: {
  kind: VariantKind
  plan?: VariantPlan
  variant?: Variant
  risks: string[]
  prompt: string
  promptDirty: boolean
  disabled: boolean
  revisionInstruction: string
  revisionMessage: string
  activeRevisionMode: PromptRevisionMode | null
  onPromptChange: (value: string) => void
  onRevisionInstructionChange: (value: string) => void
  onPromptRevision: (mode: PromptRevisionMode) => void
}) {
  const stable = kind === 'STABLE'
  const shots = plan?.shots ?? []
  const first = shots[0]
  return <section className={`plan-panel ${stable ? 'plan-panel--stable' : 'plan-panel--dynamic'}`}>
    <header><span className={`variant-label ${stable ? 'variant-label--a' : 'variant-label--b'}`}>{stable ? 'A' : 'B'}</span><div><h3>{stable ? '稳定展示' : '动态广告'}</h3><p>{stable ? '保持人物稳定与服装结构准确，清晰展示印花和版型' : '强化广告开场、动作变化和节奏，同时保持服装准确'}</p></div></header>
    <div className="plan-facts"><div><span>{stable ? '视频开场' : '开场钩子'}</span><strong>{first?.shotFunction ?? (stable ? '清晰产品开场' : '强动态广告开场')}</strong></div><div><span>人物动作</span><strong>{first?.action ?? '自然动作'}</strong></div><div><span>镜头运动</span><strong>{first?.camera ?? '稳定运镜'}</strong></div><div><span>展示重点</span><strong>{first?.productDisplay ?? '服装轮廓与细节'}</strong></div></div>
    {shots.length > 1 ? <div className="shot-strip">{shots.map((shot, index) => <span key={`${shot.shotFunction}-${index}`}><strong>镜头 {index + 1}</strong><small>{shot.action}</small></span>)}</div> : null}
    <div className={`risk-line ${risks.length ? 'risk-line--warning' : ''}`}>{risks.length ? <AlertTriangle size={15} /> : <ShieldCheck size={15} />}<span>{risks.length ? `风险提示：${formatRiskFlags(risks)}` : '未发现明显的产品准确性风险'}</span></div>
    {variant ? <><PromptBlock variant={variant} value={prompt} dirty={promptDirty} disabled={disabled} onChange={onPromptChange} /><PromptRevision kind={kind} instruction={revisionInstruction} message={revisionMessage} disabled={disabled} activeMode={activeRevisionMode} onInstructionChange={onRevisionInstructionChange} onSubmit={onPromptRevision} /></> : null}
  </section>
}

function VariantStatus({ task, variant, onChanged, onPlay }: { task: Task; variant: Variant; onChanged: () => Promise<void>; onPlay: () => void }) {
  const [busy, setBusy] = useState(false)
  const ready = Boolean(variant.downloadArtifactId)
  const unknown = variant.generationStatus === 'UNKNOWN'
  const downloading = variant.downloadStatus === 'DOWNLOADING'
  const restore = async () => {
    setBusy(true)
    try { await restoreOutput(task.id, variant.kind); await onChanged() } finally { setBusy(false) }
  }
  return <div className="variant-status"><span className={`variant-label ${variant.kind === 'STABLE' ? 'variant-label--a' : 'variant-label--b'}`}>{variant.kind === 'STABLE' ? 'A' : 'B'}</span><div><strong>{variant.kind === 'STABLE' ? '稳定展示' : '动态广告'}</strong><StatusBadge value={variant.generationStatus} /><small>{unknown ? '暂时无法确认生成状态' : variant.errorCode ?? (ready ? '成品文件已就绪' : '正在等待 LibTV 返回结果')}</small></div><div className="variant-status-actions">
    {ready ? <><button className="compact-button" onClick={onPlay}><Play size={15} />播放</button><button className="compact-button" onClick={() => void saveArtifact(variant.downloadArtifactId!, `${task.title}-${variant.kind.toLowerCase()}.mp4`)}><Download size={15} />下载</button></> : null}
    {downloading ? <button className="compact-button" disabled><LoaderCircle className="spin" size={15} />下载中</button> : null}
    {variant.generationStatus === 'SUCCEEDED' && !ready && !downloading ? <button className="compact-button" disabled={busy} onClick={() => void restore()}>{busy ? <LoaderCircle className="spin" size={15} /> : <RefreshCw size={15} />}下载结果</button> : null}
    {unknown ? <button className="compact-button" onClick={() => void onChanged()}><RefreshCw size={15} />重新查询状态</button> : null}
  </div></div>
}

function HistoricalPrompt({
  variant,
  selected,
}: {
  variant: Variant
  selected: boolean
}) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    await navigator.clipboard.writeText(variant.promptText)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1600)
  }
  const stable = variant.kind === 'STABLE'
  return <article className={`history-prompt${selected ? ' is-selected' : ''}`}>
    <header>
      <span className={`variant-label ${stable ? 'variant-label--a' : 'variant-label--b'}`}>{stable ? 'A' : 'B'}</span>
      <span><strong>{stable ? '稳定展示' : '动态广告'}</strong><small>{selected ? '将复用此提示词' : '本次不复用'}</small></span>
      <button className="compact-button" type="button" onClick={() => void copy()}>{copied ? <Check size={15} /> : <Copy size={15} />}{copied ? '已复制' : '复制'}</button>
    </header>
    <p>{variant.promptText}</p>
  </article>
}

function AnalysisProgress({ task }: { task: Task }) {
  const [now, setNow] = useState(Date.now)
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 10_000)
    return () => window.clearInterval(timer)
  }, [])
  const lastActiveAt = task.analysisHeartbeatAt ?? task.analysisStartedAt ?? task.updatedAt
  const elapsedSeconds = Math.max(0, Math.floor((now - parseTaskTimestamp(lastActiveAt)) / 1000))
  const manyImages = task.assetCount > 4
  const longRunning = task.analysisStartedAt !== null
    && now - parseTaskTimestamp(task.analysisStartedAt) >= 120_000
  const stageLabel = task.analysisStage ? analysisStageLabels[task.analysisStage] : undefined
  const activeText = elapsedSeconds < 45
    ? '刚刚'
    : `${formatElapsed(lastActiveAt, now)}前`
  return <div className="detail-analysis" role="status" aria-live="polite">
    <LoaderCircle className="spin" size={24} />
    <div>
      <strong>{stageLabel ?? (longRunning ? '后台仍在分析，已自动查询状态' : `正在分析 ${task.assetCount} 张素材`)}</strong>
      <span>{longRunning
        ? `后台任务仍在运行，最近一次活跃于${activeText}；页面会持续查询状态。`
        : manyImages
          ? '素材较多，系统已按数量延长等待时间；完成后进入方案确认。'
          : `正在识别服装结构、人物场景和适合的视频动作，最近一次活跃于${activeText}。`}</span>
    </div>
  </div>
}

function ProductionWorkspace({ task, onClose, onChanged, onRemix, onReuse, onPlay }: { task: Task; onClose: () => void; onChanged: () => Promise<void>; onRemix: () => void; onReuse: (variants: VariantKind[]) => void; onPlay: (variant: Variant) => void }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const reusableVariants = task.variants.filter((variant) => variant.promptText.trim())
  const [reuseKinds, setReuseKinds] = useState<VariantKind[]>(() => reusableVariants.map((variant) => variant.kind))
  const [confirmationKinds, setConfirmationKinds] = useState<VariantKind[]>(() => task.variants.map((variant) => variant.kind))
  const [promptDrafts, setPromptDrafts] = useState(() => ({
    stable: taskPrompt(task, 'STABLE'),
    dynamic: taskPrompt(task, 'DYNAMIC'),
  }))
  const [promptDirty, setPromptDirty] = useState<Record<VariantKind, boolean>>({ STABLE: false, DYNAMIC: false })
  const [revisionInstructions, setRevisionInstructions] = useState<Record<VariantKind, string>>({ STABLE: '', DYNAMIC: '' })
  const [revisionMessages, setRevisionMessages] = useState<Record<VariantKind, string>>({ STABLE: '', DYNAMIC: '' })
  const [activeRevision, setActiveRevision] = useState<{ kind: VariantKind; mode: PromptRevisionMode } | null>(null)
  const promptsDirty = promptDirty.STABLE || promptDirty.DYNAMIC
  const analysis = task.analysisResult as AnalysisResult | null
  const stable = task.variants.find((variant) => variant.kind === 'STABLE')
  const dynamic = task.variants.find((variant) => variant.kind === 'DYNAMIC')
  const savePrompts = async (sourceTask = task) => {
    if (!promptDrafts.stable.trim() || !promptDrafts.dynamic.trim()) throw new Error('A/B 提示词不能为空')
    const changed = await saveTaskPrompts(sourceTask, promptDrafts.stable, promptDrafts.dynamic)
    setPromptDrafts({
      stable: taskPrompt(changed, 'STABLE'),
      dynamic: taskPrompt(changed, 'DYNAMIC'),
    })
    return changed
  }
  const revisePrompt = async (kind: VariantKind, mode: PromptRevisionMode) => {
    const typedInstruction = revisionInstructions[kind].trim()
    if (mode === 'MODIFY' && !typedInstruction) {
      setError('请先用一句话描述想怎么修改')
      return
    }
    const instruction = mode === 'MODIFY'
      ? typedInstruction
      : `重新生成${kind === 'STABLE' ? '稳定展示' : '动态广告'}方案，在不改变服装事实和方案定位的前提下优化动作、镜头和节奏。`
    setBusy(true)
    setActiveRevision({ kind, mode })
    setError('')
    setRevisionMessages((current) => ({ ...current, [kind]: '' }))
    try {
      const result = await runPromptAssistant(task, 'REGENERATE', instruction, promptDrafts.stable, promptDrafts.dynamic, kind)
      setPromptDrafts({
        stable: taskPrompt(result.task, 'STABLE'),
        dynamic: taskPrompt(result.task, 'DYNAMIC'),
      })
      setPromptDirty({ STABLE: false, DYNAMIC: false })
      setRevisionMessages((current) => ({ ...current, [kind]: mode === 'MODIFY' ? '已按这句话修改此方案' : '已重新生成此方案' }))
      if (mode === 'MODIFY') setRevisionInstructions((current) => ({ ...current, [kind]: '' }))
      await onChanged()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '大模型处理失败，请稍后重试')
    } finally {
      setBusy(false)
      setActiveRevision(null)
    }
  }
  const confirm = async () => {
    setBusy(true)
    setError('')
    try {
      const currentTask = promptsDirty ? await savePrompts() : task
      await confirmTask(currentTask, confirmationKinds)
      await onChanged()
    } catch (cause) { setError(cause instanceof Error ? cause.message : '确认失败，请稍后重试') } finally { setBusy(false) }
  }
  const retryAnalysis = async () => {
    setBusy(true)
    setError('')
    try {
      await analyzeTask(task)
      await onChanged()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '重新分析启动失败，请稍后重试')
    } finally { setBusy(false) }
  }
  const isConfirmation = task.phase === 'AWAITING_CONFIRMATION'
  const isGenerating = ACTIVE_PHASES.has(task.phase) && task.phase !== 'DRAFT' && task.phase !== 'ANALYZING'
  const isCompleted = RESULT_PHASES.has(task.phase)
  const canReuse = isCompleted && task.actionCapabilities.canRegenerate && reusableVariants.length > 0
  const analysisFailure = isAnalysisFailure(task)
  const currentStep = task.phase === 'DRAFT' ? 0 : task.phase === 'ANALYZING' || analysisFailure ? 1 : isConfirmation ? 2 : RESULT_PHASES.has(task.phase) ? 4 : 3
  const needsRecovery = task.phase === 'ACTION_REQUIRED'
  const confirmationChoice = confirmationKinds.length === 2
    ? 'BOTH'
    : confirmationKinds[0] ?? task.variants[0]?.kind
  const confirmationLabel = confirmationKinds.length === 2
    ? '2 版'
    : confirmationKinds[0] === 'STABLE' ? 'A 版' : 'B 版'
  return <div className="workspace-view">
    <section className="production-workspace" aria-labelledby="detail-title">
      <header className="drawer-header">
        <button className="icon-button" onClick={onClose} aria-label="关闭任务详情"><ArrowLeft size={19} /></button>
        <div className="drawer-header-main"><span>任务 / {isConfirmation ? '方案确认' : RESULT_PHASES.has(task.phase) ? '视频结果' : analysisFailure ? '分析恢复' : needsRecovery ? '异常处理' : '生产进度'}</span><h1 id="detail-title">{task.title}</h1></div>
        <div className="drawer-header-actions"><TaskStatusBadge task={task} /></div>
      </header>
      <div className="workspace-stages" aria-label="制作阶段">{['素材', '分析', '方案', '生成', '结果'].map((label, index) => <div key={label} aria-current={index === currentStep ? 'step' : undefined} className={index < currentStep ? 'is-complete' : index === currentStep ? 'is-current' : ''}><span>{index < currentStep ? <Check size={14} /> : index + 1}</span><strong>{label}</strong></div>)}</div>
      <div className="drawer-content">
        <section className="source-summary"><div className="source-assets">{[...task.assets].sort((a, b) => a.order - b.order).map((asset, index) => <figure key={asset.id}><AuthenticatedImage src={asset.thumbnailUrl} alt={asset.originalFilename} /><figcaption>{asset.role === 'PRODUCT' || asset.usedForGeneration === false ? '产品图' : `分镜 ${index + 1}`}</figcaption></figure>)}</div><div className="garment-summary"><span>服装识别摘要</span><strong>{[analysis?.garmentFacts?.category, analysis?.garmentFacts?.mainColor, analysis?.garmentFacts?.fit].filter(Boolean).join(' · ') || '正在整理服装信息'}</strong><p>{analysis?.consistencyObservations?.summary ?? '系统将优先保持服装结构、颜色、印花和文字准确。'}</p></div></section>
        {analysisFailure ? <section className="analysis-recovery" role="alert">
          <span className="analysis-recovery-icon"><AlertTriangle size={22} /></span>
          <div><span>方案尚未生成</span><h2>{taskStatus(task).label}</h2><p>{taskFailureMessage(task)} 重新分析会继续使用当前素材，并按素材数量重新计算等待时间。</p></div>
          <button className="primary-button" disabled={busy || !task.actionCapabilities.canRetryAnalysis} onClick={() => void retryAnalysis()}>{busy ? <LoaderCircle className="spin" size={17} /> : <RefreshCw size={17} />}重新分析方案</button>
        </section> : null}
        {isConfirmation ? <>
          <div className="drawer-section-title"><div><span>步骤 2 / 3</span><h2>确认视频方案</h2></div><p>确认后将保存提示词原文快照，并原样提交给 LibTV。</p></div>
          <div className={`plans-grid${task.variants.length === 1 ? ' plans-grid--single' : ''}`}>
            {stable ? <PlanPanel kind="STABLE" plan={analysis?.stablePlan} variant={stable} risks={analysis?.riskFlags ?? []} prompt={promptDrafts.stable} promptDirty={promptDirty.STABLE} disabled={busy} revisionInstruction={revisionInstructions.STABLE} revisionMessage={revisionMessages.STABLE} activeRevisionMode={activeRevision?.kind === 'STABLE' ? activeRevision.mode : null} onPromptChange={(value) => { setPromptDrafts((current) => ({ ...current, stable: value })); setPromptDirty((current) => ({ ...current, STABLE: true })) }} onRevisionInstructionChange={(value) => setRevisionInstructions((current) => ({ ...current, STABLE: value }))} onPromptRevision={(mode) => void revisePrompt('STABLE', mode)} /> : null}
            {dynamic ? <PlanPanel kind="DYNAMIC" plan={analysis?.dynamicPlan} variant={dynamic} risks={analysis?.riskFlags ?? []} prompt={promptDrafts.dynamic} promptDirty={promptDirty.DYNAMIC} disabled={busy} revisionInstruction={revisionInstructions.DYNAMIC} revisionMessage={revisionMessages.DYNAMIC} activeRevisionMode={activeRevision?.kind === 'DYNAMIC' ? activeRevision.mode : null} onPromptChange={(value) => { setPromptDrafts((current) => ({ ...current, dynamic: value })); setPromptDirty((current) => ({ ...current, DYNAMIC: true })) }} onRevisionInstructionChange={(value) => setRevisionInstructions((current) => ({ ...current, DYNAMIC: value }))} onPromptRevision={(mode) => void revisePrompt('DYNAMIC', mode)} /> : null}
          </div>
        </> : null}
        {isGenerating || RESULT_PHASES.has(task.phase) || (task.phase === 'ACTION_REQUIRED' && !analysisFailure) ? <>
          <div className="drawer-section-title"><div><span>步骤 3 / 3</span><h2>{RESULT_PHASES.has(task.phase) ? '视频结果' : needsRecovery ? '任务需要处理' : '视频生成进度'}</h2></div></div>
          <TaskTimingTimeline task={task} />
          <div className="variant-status-list">{task.variants.map((variant) => <VariantStatus key={variant.id} task={task} variant={variant} onChanged={onChanged} onPlay={() => onPlay(variant)} />)}</div>
        </> : null}
        {isCompleted && reusableVariants.length ? <>
          <div className="drawer-section-title history-prompt-title"><div><span>历史方案</span><h2>本次使用的提示词</h2></div><p>提示词为任务完成时的只读快照</p></div>
          <div className={`history-prompts${reusableVariants.length === 1 ? ' history-prompts--single' : ''}`}>
            {reusableVariants.map((variant) => <HistoricalPrompt key={variant.id} variant={variant} selected={reuseKinds.includes(variant.kind)} />)}
          </div>
        </> : null}
        {task.phase === 'ANALYZING' ? <AnalysisProgress task={task} /> : null}
        {error ? <div className="inline-alert inline-alert--danger" role="alert"><AlertTriangle size={17} />{error}</div> : null}
        <details className="technical-details"><summary><span><MoreHorizontal size={17} />技术信息</span><ChevronRight size={16} /></summary><div><dl><dt>Task ID</dt><dd>{task.id}</dd><dt>Session ID</dt><dd>{task.clientTaskId}</dd><dt>画布 UUID</dt><dd>{task.canvasProjectUuid ?? '尚未分配'}</dd><dt>原始状态</dt><dd>{task.phase}</dd><dt>状态版本</dt><dd>{task.stateVersion}</dd><dt>错误代码</dt><dd>{task.phaseReasonCode ?? '无'}</dd></dl><div className="prompt-hashes">{task.variants.map((variant) => <span key={variant.id}><strong>{variant.kind} Prompt Hash</strong><code>{variant.promptHash ?? '尚未锁定'}</code></span>)}</div></div></details>
      </div>
      {task.actionCapabilities.canRegenerate || isConfirmation ? <footer className={`drawer-footer${canReuse ? ' drawer-footer--reuse' : ''}${isConfirmation ? ' drawer-footer--confirmation' : ''}`}>
        <div className="drawer-footer-actions">
          {task.actionCapabilities.canRegenerate && !canReuse ? <button className="secondary-button" onClick={onRemix}><RotateCcw size={16} />使用相同素材再制作</button> : null}
        </div>
        {canReuse ? <div className="reuse-controls">
          <fieldset>
            <legend>选择复用版本</legend>
            {(['STABLE', 'DYNAMIC'] as VariantKind[]).map((kind) => {
              const available = reusableVariants.some((variant) => variant.kind === kind)
              const checked = reuseKinds.includes(kind)
              return <label key={kind} className={`${checked ? 'is-selected' : ''}${available ? '' : ' is-disabled'}`}>
                <input
                  type="checkbox"
                  checked={checked}
                  disabled={!available}
                  onChange={() => setReuseKinds((current) => checked ? current.filter((item) => item !== kind) : [...current, kind].sort((a) => a === 'STABLE' ? -1 : 1))}
                />
                <span className={`variant-label ${kind === 'STABLE' ? 'variant-label--a' : 'variant-label--b'}`}>{kind === 'STABLE' ? 'A' : 'B'}</span>
                <span><strong>{kind === 'STABLE' ? '稳定展示' : '动态广告'}</strong>{!available ? <small>无历史提示词</small> : null}</span>
              </label>
            })}
          </fieldset>
          <div>
            {!reuseKinds.length ? <small role="alert">请至少勾选一个版本</small> : <small>将复用全部素材及所选提示词，并跳过图片分析</small>}
            <button className="primary-button primary-button--large" disabled={!reuseKinds.length} onClick={() => onReuse(reuseKinds)}><RotateCcw size={17} />一键复用并生成 {reuseKinds.length || ''} 版</button>
          </div>
        </div> : null}
        {isConfirmation ? <div className="confirmation-submit">
          {task.variants.length > 1 ? <fieldset className="confirmation-variant-picker">
            <legend>本次生成</legend>
            <div>
              <label className={confirmationChoice === 'STABLE' ? 'is-selected' : ''}>
                <input type="radio" name={`confirmation-variant-${task.id}`} checked={confirmationChoice === 'STABLE'} disabled={busy} onChange={() => setConfirmationKinds(['STABLE'])} />
                <span>仅 A</span>
              </label>
              <label className={confirmationChoice === 'BOTH' ? 'is-selected' : ''}>
                <input type="radio" name={`confirmation-variant-${task.id}`} checked={confirmationChoice === 'BOTH'} disabled={busy} onChange={() => setConfirmationKinds(['STABLE', 'DYNAMIC'])} />
                <span>A+B</span>
              </label>
              <label className={confirmationChoice === 'DYNAMIC' ? 'is-selected' : ''}>
                <input type="radio" name={`confirmation-variant-${task.id}`} checked={confirmationChoice === 'DYNAMIC'} disabled={busy} onChange={() => setConfirmationKinds(['DYNAMIC'])} />
                <span>仅 B</span>
              </label>
            </div>
          </fieldset> : null}
          <button className="primary-button primary-button--large" disabled={busy} onClick={() => void confirm()}>{busy ? <LoaderCircle className="spin" size={18} /> : <Check size={18} />}确认并生成 {confirmationLabel}</button>
        </div> : null}
      </footer> : null}
    </section>
  </div>
}

function HomeView({ tasks, seed, system, onCreated, onOpen, onView, onPlay, onRemix, onFeedbackChanged }: { tasks: Task[]; seed: RemixSeed | null; system: SystemStatus | null; onCreated: (task: Task, open?: boolean) => void; onOpen: (task: Task) => void; onView: (view: View) => void; onPlay: (task: Task, variant: Variant) => void; onRemix: (task: Task) => void; onFeedbackChanged: (task: Task) => void }) {
  const actionableTasks = tasks.filter((task) => task.phase === 'AWAITING_CONFIRMATION' || task.phase === 'ACTION_REQUIRED' || task.variants.some((variant) => variant.generationStatus === 'UNKNOWN'))
  const attentionSignatureFor = (task: Task) => [
    task.phase,
    task.phaseReasonCode ?? '',
    ...task.variants.flatMap((variant) => [variant.kind, variant.generationStatus, variant.errorCode ?? '']),
  ].join(':')
  const [dismissedAttentionItems, setDismissedAttentionItems] = useState<Record<string, string>>(() => {
    try {
      return JSON.parse(localStorage.getItem(DISMISSED_ATTENTION_ITEMS_STORAGE_KEY) ?? '{}') as Record<string, string>
    } catch {
      return {}
    }
  })
  const needsAction = actionableTasks
    .filter((task) => dismissedAttentionItems[task.id] !== attentionSignatureFor(task))
    .slice(0, 3)
  const background = tasks.filter((task) => ACTIVE_PHASES.has(task.phase) && !needsAction.some((item) => item.id === task.id)).slice(0, Math.max(0, 5 - needsAction.length))
  const results = tasks.filter((task) => COMPLETED_PHASES.has(task.phase)).flatMap((task) => task.variants.map((variant) => ({ task, variant }))).filter(({ variant }) => variant.downloadArtifactId).slice(0, 6)
  const activeCount = tasks.filter((task) => ACTIVE_PHASES.has(task.phase)).length
  const completedCount = tasks.filter((task) => COMPLETED_PHASES.has(task.phase)).length
  const attentionSignature = needsAction.map((task) => `${task.id}:${task.phase}:${task.variants.some((variant) => variant.generationStatus === 'UNKNOWN')}`).sort().join('|')
  const [dismissedAttention, setDismissedAttention] = useState(() => sessionStorage.getItem(DISMISSED_ATTENTION_STORAGE_KEY) ?? '')
  const showAttention = Boolean(needsAction.length && attentionSignature !== dismissedAttention)
  const dismissAttention = () => {
    sessionStorage.setItem(DISMISSED_ATTENTION_STORAGE_KEY, attentionSignature)
    setDismissedAttention(attentionSignature)
  }
  const dismissAttentionItem = (task: Task) => {
    setDismissedAttentionItems((current) => {
      const next = { ...current, [task.id]: attentionSignatureFor(task) }
      localStorage.setItem(DISMISSED_ATTENTION_ITEMS_STORAGE_KEY, JSON.stringify(next))
      return next
    })
  }
  return <div className="home-view">
    <div className="home-title"><div><span className="page-eyebrow">Creative Production</span><h1>开始制作</h1><p>上传素材，创建一条服装广告视频。</p></div><div className="home-title-actions"><span className="quick-stat"><strong>{activeCount}</strong><small>处理中</small></span><span className="quick-stat"><strong>{completedCount}</strong><small>已完成</small></span><button className="text-button" onClick={() => onView('records')}>查看任务<ChevronRight size={15} /></button></div></div>
    <div className="home-hero-grid home-hero-grid--full">
      <ProductionComposer key={seed?.id ?? 'new-production'} seed={seed} onCreated={onCreated} system={system} />
    </div>
    {showAttention ? <section className="attention-panel" aria-label="待处理任务">
      <SectionHeading title="需要你操作" count={needsAction.length} action={<div className="attention-panel-actions"><button className="text-button" onClick={() => onView('records')}>查看全部<ChevronRight size={15} /></button><button className="icon-button attention-dismiss" onClick={dismissAttention} aria-label="暂时收起待处理任务" title="暂时收起"><X size={18} /></button></div>} />
      <p>这些是之前创建、目前暂停等待处理的任务，不影响你继续制作新视频。</p>
      <div className="attention-list">{needsAction.map((task) => <AttentionItem key={task.id} task={task} onOpen={() => onOpen(task)} onDismiss={() => dismissAttentionItem(task)} />)}</div>
    </section> : null}
    {background.length ? <section className="home-section background-work"><SectionHeading title="后台处理中" count={background.length} action={<button className="text-button" onClick={() => onView('records')}>查看全部<ChevronRight size={15} /></button>} /><div className="processing-list" aria-live="polite">{background.map((task) => <ProcessingRow key={task.id} task={task} onOpen={() => onOpen(task)} />)}</div></section> : null}
    <section className="home-section"><SectionHeading title="最近完成" action={<button className="text-button" onClick={() => onView('records')}>查看全部记录<ChevronRight size={15} /></button>} />{results.length ? <div className="results-grid">{results.map(({ task, variant }) => <ResultCard key={variant.id} task={task} variant={variant} onPlay={() => onPlay(task, variant)} onRemix={() => onRemix(task)} onOpen={() => onOpen(task)} onFeedbackChanged={onFeedbackChanged} />)}</div> : <EmptyState icon={<Film size={24} />} title="还没有生成结果" description="完成第一条服装广告视频后，结果会出现在这里。" />}</section>
  </div>
}

function EmptyState({ icon, title, description }: { icon: React.ReactNode; title: string; description: string }) {
  return <div className="empty-state"><span>{icon}</span><strong>{title}</strong><p>{description}</p></div>
}

function RecordsView({ tasks, hasMore, loadingMore, onLoadMore, onOpen, onPlay, onRemix, onFeedbackChanged }: { tasks: Task[]; hasMore: boolean; loadingMore: boolean; onLoadMore: () => void; onOpen: (task: Task) => void; onPlay: (task: Task, variant: Variant) => void; onRemix: (task: Task) => void; onFeedbackChanged: (task: Task) => void }) {
  const [filter, setFilter] = useState<RecordFilter>('all')
  const [query, setQuery] = useState('')
  const groups: Array<{ value: RecordFilter; label: string; test: (task: Task) => boolean }> = [
    { value: 'all', label: '全部', test: () => true },
    { value: 'attention', label: '需要确认', test: (task) => task.phase === 'AWAITING_CONFIRMATION' },
    { value: 'active', label: '处理中', test: (task) => ACTIVE_PHASES.has(task.phase) },
    { value: 'partial', label: '部分完成', test: (task) => task.phase === 'PARTIALLY_DELIVERABLE' },
    { value: 'done', label: '已完成', test: (task) => COMPLETED_PHASES.has(task.phase) },
    { value: 'failed', label: '失败', test: (task) => FAILED_PHASES.has(task.phase) },
    { value: 'cancelled', label: '已取消', test: (task) => task.phase === 'CANCELLED' },
  ]
  const group = groups.find((item) => item.value === filter)!
  const visible = tasks.filter((task) => group.test(task) && task.title.toLowerCase().includes(query.trim().toLowerCase()))
  const completed = visible.filter((task) => COMPLETED_PHASES.has(task.phase))
  const listRows = filter === 'done' ? [] : visible.filter((task) => !COMPLETED_PHASES.has(task.phase))
  const completedResults = completed.flatMap((task) => task.variants.map((variant) => ({ task, variant }))).filter(({ variant }) => variant.downloadArtifactId)
  const attentionCount = tasks.filter((task) => task.phase === 'AWAITING_CONFIRMATION' || task.phase === 'ACTION_REQUIRED').length
  const activeCount = tasks.filter((task) => ACTIVE_PHASES.has(task.phase)).length
  const doneCount = tasks.filter((task) => COMPLETED_PHASES.has(task.phase)).length
  return <div className="page-view"><div className="page-title"><div><span>Production Tasks</span><h1>任务</h1><p>查找任务、继续处理，或直接播放和下载已完成视频。</p></div><label className="search-field"><Search size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索任务名称" aria-label="搜索任务名称" /></label></div>
    <section className="records-overview" aria-label="任务概览">
      <div><span className="records-overview-dot is-blue" /><span><small>全部任务</small><strong>{tasks.length}</strong></span></div>
      <div><span className="records-overview-dot is-amber" /><span><small>需要处理</small><strong>{attentionCount}</strong></span></div>
      <div><span className="records-overview-dot is-purple" /><span><small>生产中</small><strong>{activeCount}</strong></span></div>
      <div><span className="records-overview-dot is-green" /><span><small>已完成</small><strong>{doneCount}</strong></span></div>
    </section>
    <div className="filter-tabs">{groups.map((item) => { const count = tasks.filter(item.test).length; return <button key={item.value} className={filter === item.value ? 'is-active' : ''} onClick={() => setFilter(item.value)}>{item.label}<span>{count}</span></button> })}</div>
    {listRows.length ? <div className="task-table"><div className="task-table-head"><span>产品 / 任务</span><span>当前状态</span><span>版本进度</span><span>更新时间</span><span /></div>{listRows.map((task) => <button className="task-table-row" key={task.id} onClick={() => onOpen(task)}><span className="task-name-cell"><TaskThumb task={task} /><span><strong>{task.title}</strong><small>{task.assetCount} 张素材</small></span></span><span><TaskStatusBadge task={task} />{task.phaseReasonCode ? <small>{isAnalysisFailure(task) ? taskFailureMessage(task) : task.phaseReasonCode}</small> : null}</span><span className="mini-variants">{task.variants.map((variant) => <i key={variant.id} className={variant.generationStatus === 'FAILED' ? 'is-failed' : variant.generationStatus === 'SUCCEEDED' ? 'is-done' : ''}>{variant.kind === 'STABLE' ? 'A' : 'B'}</i>)}</span><span>{formatTime(task.updatedAt)}</span><span><ChevronRight size={17} /></span></button>)}</div> : null}
    {completedResults.length ? <section className="records-completed"><SectionHeading title={filter === 'all' ? '已完成' : '视频结果'} count={completedResults.length} /><div className="results-grid results-grid--library">{completedResults.map(({ task, variant }) => <ResultCard key={variant.id} task={task} variant={variant} onPlay={() => onPlay(task, variant)} onRemix={() => onRemix(task)} onOpen={() => onOpen(task)} onFeedbackChanged={onFeedbackChanged} />)}</div></section> : null}
    {hasMore ? <div className="records-load-more"><button className="secondary-button" disabled={loadingMore} onClick={onLoadMore}>{loadingMore ? <LoaderCircle className="spin" size={16} /> : null}{loadingMore ? '正在加载' : '加载更早记录'}</button></div> : null}
    {!visible.length ? <EmptyState icon={<ListVideo size={24} />} title={`没有${group.label === '全部' ? '' : group.label}记录`} description="任务状态变化后会自动归入对应分类。" /> : null}
  </div>
}

function ProviderCredentials({ adminId }: { adminId: string | null }) {
  const [status, setStatus] = useState<AdminCredentialsStatus | null>(null)
  const [libtvKey, setLibtvKey] = useState('')
  const [modelKey, setModelKey] = useState('')
  const [modelBaseUrl, setModelBaseUrl] = useState('')
  const [baseUrlError, setBaseUrlError] = useState('')
  const [showLibtv, setShowLibtv] = useState(false)
  const [showModel, setShowModel] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    let active = true
    getAdminCredentials(adminId)
      .then((next) => { if (active) { setStatus(next); setModelBaseUrl(next.modelBaseUrl ?? ''); setError('') } })
      .catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : '无法读取管理员配置') })
    return () => { active = false }
  }, [adminId])

  const save = async (event?: FormEvent<HTMLFormElement>) => {
    event?.preventDefault()
    const libtvAccessKey = libtvKey.trim()
    const modelApiKey = modelKey.trim()
    const normalizedBaseUrl = modelBaseUrl.trim()
    const baseUrlChanged = normalizedBaseUrl !== (status?.modelBaseUrl ?? '')
    const nextBaseUrlError = validateCompatibleBaseUrl(normalizedBaseUrl)
    setBaseUrlError(nextBaseUrlError)
    if (nextBaseUrlError) return
    if (!libtvAccessKey && !modelApiKey && !baseUrlChanged) {
      setError('请至少更新一个服务配置')
      return
    }
    setBusy(true)
    setError('')
    setSaved(false)
    try {
      const next = await updateAdminCredentials(adminId, {
        ...(libtvAccessKey ? { libtvAccessKey } : {}),
        ...(modelApiKey ? { modelApiKey } : {}),
        ...(baseUrlChanged && normalizedBaseUrl ? { modelBaseUrl: normalizedBaseUrl } : {}),
        ...(baseUrlChanged && !normalizedBaseUrl ? { clearModelBaseUrl: true } : {}),
      })
      setStatus(next)
      setModelBaseUrl(next.modelBaseUrl ?? '')
      setLibtvKey('')
      setModelKey('')
      setSaved(true)
      window.setTimeout(() => setSaved(false), 2200)
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Key 保存失败') }
    finally { setBusy(false) }
  }

  const credentialState = (configured: boolean | undefined) => {
    if (status === null && !error) return '正在读取'
    return configured ? '已配置' : '未配置'
  }
  const hasChanges = Boolean(
    libtvKey.trim()
    || modelKey.trim()
    || modelBaseUrl.trim() !== (status?.modelBaseUrl ?? ''),
  )

  return <form className="settings-section credential-section" onSubmit={(event) => void save(event)}>
    <div className="settings-section-heading">
      <div><span>仅管理员</span><h2>服务凭据</h2><p>Key 只保存在服务端且不会回显；Base URL 会显示当前配置。留空 Key 不会覆盖原值。</p></div>
      <button className="primary-button" type="submit" disabled={busy || !hasChanges}>{busy ? <LoaderCircle className="spin" size={16} /> : saved ? <Check size={16} /> : <LockKeyhole size={16} />}{busy ? '正在保存' : saved ? '已安全保存' : '保存配置'}</button>
    </div>
    <div className="credential-grid">
      <div className="credential-field">
        <label htmlFor="libtv-access-key"><strong>LibTV Access Key</strong><small className={status?.libtvConfigured ? 'is-configured' : ''}>{credentialState(status?.libtvConfigured)}</small></label>
        <div className="secret-input"><LockKeyhole size={16} /><input id="libtv-access-key" type={showLibtv ? 'text' : 'password'} value={libtvKey} onChange={(event) => setLibtvKey(event.target.value)} placeholder={status?.libtvConfigured ? '输入新 Key 以替换当前配置' : '输入 LibTV Access Key'} autoComplete="new-password" spellCheck={false} minLength={8} maxLength={4096} aria-describedby="libtv-key-help" /><button type="button" onClick={() => setShowLibtv((value) => !value)} aria-label={showLibtv ? '隐藏 LibTV Key' : '显示 LibTV Key'} title={showLibtv ? '隐藏' : '显示'}>{showLibtv ? <EyeOff size={16} /> : <Eye size={16} />}</button></div>
        <small id="libtv-key-help">用于管理员账号下的 LibTV 视频生成服务。</small>
      </div>
      <div className="credential-field">
        <label htmlFor="model-api-key"><strong>大模型 API Key</strong><small className={status?.modelConfigured ? 'is-configured' : ''}>{credentialState(status?.modelConfigured)}</small></label>
        <div className="secret-input"><LockKeyhole size={16} /><input id="model-api-key" type={showModel ? 'text' : 'password'} value={modelKey} onChange={(event) => setModelKey(event.target.value)} placeholder={status?.modelConfigured ? '输入新 Key 以替换当前配置' : '输入大模型 API Key'} autoComplete="new-password" spellCheck={false} minLength={8} maxLength={4096} aria-describedby="model-key-help" /><button type="button" onClick={() => setShowModel((value) => !value)} aria-label={showModel ? '隐藏大模型 Key' : '显示大模型 Key'} title={showModel ? '隐藏' : '显示'}>{showModel ? <EyeOff size={16} /> : <Eye size={16} />}</button></div>
        <small id="model-key-help">用于服装、人物、场景分析和视频方案生成。</small>
      </div>
      <div className="credential-field credential-field--wide">
        <label htmlFor="model-base-url"><strong>OpenAI 兼容 Base URL</strong><small>{status?.modelBaseUrl ? '自定义' : '官方默认'}</small></label>
        <div className="secret-input"><Globe2 size={16} /><input id="model-base-url" type="url" value={modelBaseUrl} onChange={(event) => { setModelBaseUrl(event.target.value); if (baseUrlError) setBaseUrlError('') }} onBlur={() => setBaseUrlError(validateCompatibleBaseUrl(modelBaseUrl))} placeholder="https://gateway.example.com/v1" autoComplete="url" spellCheck={false} maxLength={2048} aria-describedby={`model-base-url-help${baseUrlError ? ' model-base-url-error' : ''}`} aria-invalid={Boolean(baseUrlError)} /></div>
        <small id="model-base-url-help">第三方 OpenAI 兼容服务需填写完整 API 根地址，通常以 /v1 结尾；留空使用官方 OpenAI。</small>
        {baseUrlError ? <small id="model-base-url-error" className="field-error" role="alert">{baseUrlError}</small> : null}
      </div>
    </div>
    <div className="credential-feedback" aria-live="polite">
      {status?.updatedAt ? <p className="credential-updated">最近更新：{formatTime(status.updatedAt)}</p> : null}
      {error ? <div className="inline-alert inline-alert--danger credential-error" role="alert"><AlertTriangle size={16} />{error}</div> : null}
    </div>
  </form>
}

function LibTVAccountSettings({ adminId }: { adminId: string }) {
  const [status, setStatus] = useState<LibTVAccountStatus | null>(null)
  const [selectedAccount, setSelectedAccount] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<'login' | 'switch' | 'refresh' | null>(null)
  const [polling, setPolling] = useState(false)
  const [loginUrl, setLoginUrl] = useState('')
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')

  const refresh = useCallback(async (showLoading = false) => {
    if (showLoading) setBusy('refresh')
    try {
      const next = await getLibTVAccountStatus(adminId)
      setStatus(next)
      setSelectedAccount(next.activeAccount?.accountId ?? '')
      setError('')
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '无法读取 LibTV 登录状态')
    } finally {
      setLoading(false)
      if (showLoading) setBusy(null)
    }
  }, [adminId])

  useEffect(() => {
    let active = true
    const initial = window.setTimeout(() => {
      if (active) void refresh()
    }, 0)
    return () => {
      active = false
      window.clearTimeout(initial)
    }
  }, [refresh])

  useEffect(() => {
    if (!polling) return
    let active = true
    let timer: number | undefined
    let attempts = 0
    const poll = async () => {
      attempts += 1
      try {
        const next = await getLibTVAccountStatus(adminId)
        if (!active) return
        setStatus(next)
        setSelectedAccount(next.activeAccount?.accountId ?? '')
        if (next.authenticated) {
          setPolling(false)
          setLoginUrl('')
          setNotice('LibTV 登录成功，当前账号信息已刷新。')
          setError('')
          return
        }
        if (!next.loginInProgress && attempts > 1) {
          setPolling(false)
          setError('登录流程已结束，但尚未检测到有效账号。请重新打开登录页。')
          return
        }
      } catch (cause) {
        if (active && attempts >= 3) {
          setPolling(false)
          setError(cause instanceof Error ? cause.message : '登录状态确认失败')
          return
        }
      }
      if (active && attempts < 120) timer = window.setTimeout(() => void poll(), 1500)
      else if (active) {
        setPolling(false)
        setError('登录等待超时，请重新打开登录页。')
      }
    }
    timer = window.setTimeout(() => void poll(), 800)
    return () => {
      active = false
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [adminId, polling])

  const openLogin = async () => {
    const popup = window.open('about:blank', 'libtv-login', 'popup,width=1100,height=760')
    if (popup) popup.opener = null
    setBusy('login')
    setNotice('')
    setError('')
    setLoginUrl('')
    try {
      const started = await startLibTVLogin(adminId)
      if (popup && !popup.closed) popup.location.replace(started.loginUrl)
      else setLoginUrl(started.loginUrl)
      setPolling(true)
      setNotice(started.alreadyRunning ? '已重新打开正在等待的登录页。' : '请在新窗口完成 LibTV 登录。')
    } catch (cause) {
      popup?.close()
      setError(cause instanceof ApiError ? cause.message : '无法启动 LibTV 登录')
    } finally { setBusy(null) }
  }

  const switchAccount = async () => {
    if (!selectedAccount || selectedAccount === status?.activeAccount?.accountId) return
    setBusy('switch')
    setNotice('')
    setError('')
    try {
      const switched = await switchLibTVAccount(adminId, selectedAccount)
      setNotice(switched.alreadyActive ? '该账号已经生效。' : `已切换到 ${switched.accountName}。`)
      await refresh()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'LibTV 账号切换失败')
    } finally { setBusy(null) }
  }

  const stateLabel = loading
    ? '正在检查'
    : status === null
      ? '状态未知'
      : !status.available
        ? '模拟模式'
        : status.authenticated
          ? '已登录'
          : polling || status.loginInProgress
            ? '等待登录'
            : '需要登录'
  const activeAccount = status?.activeAccount
  return <section className="settings-section libtv-account-section">
    <div className="settings-section-heading">
      <div><span>LibTV 账号</span><h2>登录与账号空间</h2><p>登录凭据只由本机官方 CLI 保存。可在这里重新登录，或切换当前用户可访问的个人与团队空间。</p></div>
      <div className="libtv-account-actions">
        <button className="secondary-button" type="button" disabled={loading || busy !== null} onClick={() => void refresh(true)}><RefreshCw className={busy === 'refresh' ? 'spin' : ''} size={16} />刷新</button>
        <button className="primary-button" type="button" disabled={loading || busy !== null || status?.available === false} onClick={() => void openLogin()}>{busy === 'login' ? <LoaderCircle className="spin" size={16} /> : <LogIn size={16} />}{status?.authenticated ? '重新登录' : '登录 LibTV'}</button>
      </div>
    </div>
    <div className="libtv-account-grid">
      <div className="libtv-account-card">
        <div className="libtv-account-card-icon"><UserRound size={20} /></div>
        <div><small>当前状态</small><strong>{activeAccount?.accountName ?? stateLabel}</strong><span>{activeAccount ? `${activeAccount.accountType}${activeAccount.teamId !== null ? ` · Team ${activeAccount.teamId}` : ''}` : status?.available === false ? '启用 real 适配器后可登录' : '通过浏览器完成官方认证'}</span></div>
        <span className={`libtv-account-state ${status?.authenticated ? 'is-connected' : ''}`}>{polling ? <LoaderCircle className="spin" size={13} /> : status?.authenticated ? <CheckCircle2 size={13} /> : <CircleAlert size={13} />}{stateLabel}</span>
      </div>
      <div className="libtv-account-switch">
        <label htmlFor="libtv-account-select"><strong>切换账号空间</strong><small>切换会影响后续 LibTV 项目和画布的默认账号范围。</small></label>
        <div>
          <select id="libtv-account-select" value={selectedAccount} disabled={!status?.authenticated || busy !== null || status.accounts.length < 2} onChange={(event) => setSelectedAccount(event.target.value)}>
            {!status?.accounts.length ? <option value="">暂无可切换账号</option> : status.accounts.map((account) => <option value={account.accountId} key={account.accountId}>{account.accountName}{account.isActive ? '（当前）' : ''}</option>)}
          </select>
          <button className="secondary-button" type="button" disabled={!selectedAccount || selectedAccount === activeAccount?.accountId || busy !== null} onClick={() => void switchAccount()}>{busy === 'switch' ? <LoaderCircle className="spin" size={16} /> : <ArrowRight size={16} />}{busy === 'switch' ? '正在切换' : '切换'}</button>
        </div>
      </div>
    </div>
    <div className="libtv-account-feedback" aria-live="polite">
      {loginUrl ? <a href={loginUrl} target="_blank" rel="noreferrer">浏览器拦截了弹窗，点击这里继续登录</a> : null}
      {notice ? <p><CheckCircle2 size={15} />{notice}</p> : null}
      {error ? <div className="inline-alert inline-alert--danger" role="alert"><AlertTriangle size={16} />{error}</div> : null}
    </div>
  </section>
}

function KlingCliSettings({ adminId, onChanged }: { adminId: string; onChanged: () => Promise<void> }) {
  const [status, setStatus] = useState<KlingStatus | null>(null)
  const [busy, setBusy] = useState<'load' | 'refresh' | 'login' | 'logout' | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const load = useCallback(async (force = false) => {
    setBusy(force ? 'refresh' : 'load')
    try {
      setStatus(force ? await refreshKlingCapabilities(adminId) : await getKlingStatus(adminId))
      setError('')
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '无法读取可灵 CLI 状态')
    } finally { setBusy(null) }
  }, [adminId])
  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [load])
  const authenticate = async () => {
    setBusy('login')
    setError('')
    setNotice('')
    try {
      setStatus(await loginKling(adminId))
      setNotice('可灵账号已登录，能力信息已更新。')
      await onChanged()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '可灵账号登录失败')
    } finally { setBusy(null) }
  }
  const signOut = async () => {
    if (!window.confirm('退出可灵账号后，生成任务将无法使用可灵，确定继续吗？')) return
    setBusy('logout')
    setError('')
    setNotice('')
    try {
      setStatus(await logoutKling(adminId))
      setNotice('已退出可灵账号。')
      await onChanged()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '退出可灵账号失败')
    } finally { setBusy(null) }
  }
  const stateLabel = status?.status === 'KLING_CLI_READY'
    ? '已就绪'
    : status?.status === 'KLING_CLI_NOT_INSTALLED'
      ? '未安装'
      : status?.status === 'KLING_CLI_NOT_AUTHENTICATED'
        ? '未登录'
        : status?.enabled
          ? '能力不可用'
          : '未启用'
  return <section className="settings-section libtv-account-section">
    <div className="settings-section-heading">
      <div><span>可灵官方 CLI</span><h2>Provider 状态与能力</h2><p>生成、查询和素材上传只通过本机官方 <code>kling</code> CLI；账号操作会打开浏览器完成 OAuth。</p></div>
      <div className="libtv-account-actions">
        <button className="secondary-button" type="button" disabled={busy !== null || !status?.enabled} onClick={() => void load(true)}><RefreshCw className={busy === 'refresh' ? 'spin' : ''} size={16} />刷新能力</button>
        <button className="secondary-button" type="button" disabled={busy !== null || !status?.authenticated} onClick={() => void signOut()}>{busy === 'logout' ? <LoaderCircle className="spin" size={16} /> : <LogOut size={16} />}退出账号</button>
        <button className="primary-button" type="button" disabled={busy !== null || !status?.enabled || status?.status === 'KLING_CLI_NOT_INSTALLED'} onClick={() => void authenticate()}>{busy === 'login' ? <LoaderCircle className="spin" size={16} /> : <LogIn size={16} />}{busy === 'login' ? '等待浏览器授权' : status?.authenticated ? '重新登录' : '登录可灵'}</button>
      </div>
    </div>
    <div className="libtv-account-grid">
      <div className="libtv-account-card">
        <div className="libtv-account-card-icon"><Clapperboard size={20} /></div>
        <div><small>当前状态</small><strong>{stateLabel}</strong><span>{status ? `${klingStatusMessage(status.status, status.reason)}${status.cliVersion ? ` · CLI ${status.cliVersion}` : ''}` : '等待能力发现'}</span></div>
        <span className={`libtv-account-state ${status?.status === 'KLING_CLI_READY' ? 'is-connected' : ''}`}>{busy !== null ? <LoaderCircle className="spin" size={13} /> : status?.status === 'KLING_CLI_READY' ? <CheckCircle2 size={13} /> : <CircleAlert size={13} />}{stateLabel}</span>
      </div>
      <div className="libtv-account-switch">
        <label><strong>当前能力</strong><small>模型和参数来自实时 <code>who_am_i</code> / <code>tool_list</code>，不会写死。</small></label>
        <div><span>{status?.supportedModels.length ? `${status.supportedModels.length} 个图生视频模型` : '尚未发现模型'}</span><span>{status?.imageInputLimit ? `最多 ${status.imageInputLimit} 张输入图` : '图片限制未知'}</span></div>
      </div>
    </div>
    <div className="libtv-account-feedback" aria-live="polite">
      {notice ? <p><CheckCircle2 size={15} />{notice}</p> : null}
      {error ? <div className="inline-alert inline-alert--danger" role="alert"><AlertTriangle size={16} />{error}</div> : null}
    </div>
  </section>
}

function BrowserNotificationSetting({
  enabled,
  permission,
  onEnable,
  onDisable,
}: {
  enabled: boolean
  permission: NotificationPermission | 'unsupported'
  onEnable: () => Promise<void>
  onDisable: () => void
}) {
  const active = enabled && permission === 'granted'
  const unavailable = permission === 'unsupported'
  const blocked = permission === 'denied'
  const description = unavailable
    ? '当前浏览器不支持系统通知。'
    : blocked
      ? '通知权限已被浏览器阻止，请在地址栏的网站权限中重新允许。'
      : active
        ? '页面切到后台时，方案待确认或视频生成完成会弹出系统通知。'
        : '开启后，即使正在查看其他页面，也能及时收到关键进度。'
  return <section className="settings-section prompt-confirmation-section">
    <div className="settings-section-heading">
      <div><span>消息提醒</span><h2>浏览器通知</h2><p>{description}</p></div>
      <label className="settings-switch" title={blocked ? '请先在浏览器的网站权限中允许通知' : undefined}>
        <input
          type="checkbox"
          checked={active}
          disabled={unavailable || blocked}
          aria-label="浏览器通知"
          onChange={(event) => event.target.checked ? void onEnable() : onDisable()}
        />
        <span aria-hidden="true" />
      </label>
    </div>
  </section>
}

function PersonalPromptConfirmationSetting() {
  const [automatic, setAutomatic] = useState(false)
  const [ready, setReady] = useState(false)
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    setBusy(true)
    try {
      const preference = await getPersonalPromptAutoConfirmation()
      setAutomatic(preference.automatic)
      setReady(true)
      setError('')
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '无法读取自动确认设置')
    } finally {
      setBusy(false)
    }
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [load])

  const toggle = async (enabled: boolean) => {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const preference = await setPersonalPromptAutoConfirmation(enabled)
      setAutomatic(preference.automatic)
      setNotice(preference.automatic
        ? '已开启，你的普通方案将跳过人工确认并直接生成。'
        : '已关闭，你的方案将在生成前等待人工确认。')
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '自动确认设置保存失败')
      await load()
    } finally {
      setBusy(false)
    }
  }

  return <section className="settings-section prompt-confirmation-section">
    <div className="settings-section-heading">
      <div><span>生成流程</span><h2>自动确认提示词</h2><p>{automatic ? '你的普通方案分析完成后会跳过人工确认，直接进入生成。需要质量复核或被系统拦截的方案仍需人工处理。' : '默认关闭。你的方案分析完成后，需要检查并确认提示词才会开始生成。'}</p></div>
      <div className="prompt-confirmation-control">
        <span className={`prompt-confirmation-state${automatic ? ' is-active' : ''}`}>{busy && !ready ? '读取中' : automatic ? '已开启' : '已关闭'}</span>
        <label className="settings-switch" title="自动确认提示词">
          <input type="checkbox" checked={automatic} disabled={busy || !ready} aria-label="自动确认提示词" onChange={(event) => void toggle(event.target.checked)} />
          <span aria-hidden="true" />
        </label>
      </div>
    </div>
    <div className="prompt-confirmation-feedback" aria-live="polite">
      {notice ? <p><CheckCircle2 size={15} />{notice}</p> : null}
      {error ? <div className="inline-alert inline-alert--danger" role="alert"><AlertTriangle size={16} />{error}</div> : null}
    </div>
  </section>
}

function SettingsView({
  system,
  onLogout,
  browserNotificationsEnabled,
  browserNotificationPermission,
  onEnableBrowserNotifications,
  onDisableBrowserNotifications,
}: {
  system: SystemStatus | null
  onLogout: () => void
  browserNotificationsEnabled: boolean
  browserNotificationPermission: NotificationPermission | 'unsupported'
  onEnableBrowserNotifications: () => Promise<void>
  onDisableBrowserNotifications: () => void
}) {
  const [saved, setSaved] = useState(false)
  const [settings, setSettings] = useState(() => ({
    model: readDefaultAnalysisModel(system?.openaiModel),
    provider: (localStorage.getItem('generation-provider') as GenerationProvider | null) ?? 'libtv',
    outputVariants: readOutputVariantSelection(),
  }))
  const save = () => {
    localStorage.setItem('default-model', settings.model.trim())
    localStorage.setItem('generation-provider', settings.provider)
    localStorage.setItem(OUTPUT_VARIANT_STORAGE_KEY, settings.outputVariants)
    ;['video-direction', 'default-ratio', 'default-duration', 'max-concurrency', 'retry-count', 'save-directory'].forEach((key) => localStorage.removeItem(key))
    setSaved(true)
    window.setTimeout(() => setSaved(false), 1800)
  }
  const klingReady = Boolean(system?.kling.available && system.kling.authenticated)
  const klingLabel = system?.kling.status === 'KLING_CLI_NOT_INSTALLED'
    ? 'Kling · CLI 未安装'
    : system?.kling.status === 'KLING_CLI_NOT_AUTHENTICATED'
      ? 'Kling · 账号未登录'
      : system?.kling.enabled
        ? 'Kling 官方 CLI'
        : 'Kling · 未启用'
  return <div className="page-view settings-view"><div className="page-title"><div><span>个人工作区</span><h1>设置</h1><p>配置默认生成偏好，减少每次制作时的重复选择。</p></div><div className="page-title-actions">{system?.sharedAuthentication ? <button className="secondary-button" onClick={onLogout}>退出登录</button> : null}<button className="primary-button" disabled={!settings.model.trim() || (settings.provider === 'kling' && !klingReady)} onClick={save}>{saved ? <Check size={17} /> : null}{saved ? '已保存' : '保存偏好'}</button></div></div>
    {saved ? <div className="save-toast" role="status" aria-live="polite"><CheckCircle2 size={17} /><span><strong>偏好已保存</strong><small>下次新建任务时自动应用</small></span></div> : null}
    <section className="settings-section settings-section--featured"><div className="settings-section-heading"><div><span>默认参数</span><h2>生成配置</h2><p>这些设置只影响后续新建任务，不会修改已经进入生产流程的任务。</p></div></div><div className="settings-grid">
      <label><span>方案分析模型</span><input name="analysis-model" value={settings.model} onChange={(event) => setSettings({ ...settings, model: event.target.value })} list="settings-model-options" maxLength={100} spellCheck={false} autoComplete="off" /><small>可输入管理员已配置 Key 支持的模型 ID</small></label>
      <label><span>视频生成工具</span><select value={settings.provider} onChange={(event) => setSettings({ ...settings, provider: event.target.value as GenerationProvider })}><option value="libtv">LibTV</option><option value="kling" disabled={!klingReady}>{klingLabel}</option></select><small>{system?.kling.status === 'KLING_CLI_READY' ? '生成通道按任务保存，不会自动切换现有 LibTV 任务' : klingStatusMessage(system?.kling.status, system?.kling.reason)}</small></label>
    </div><datalist id="settings-model-options"><option value={system?.openaiModel ?? DEFAULT_ANALYSIS_MODEL} /></datalist>
      <div className="generation-contract" aria-label="默认生成参数">
        <span><strong>9:16</strong><small>固定比例</small></span>
        <span><strong>10 秒</strong><small>固定时长</small></span>
        <label htmlFor="output-variants">
          <span>输出版本</span>
          <select id="output-variants" value={settings.outputVariants} onChange={(event) => setSettings({ ...settings, outputVariants: event.target.value as OutputVariantSelection })}>
            <option value="stable">一版 · A 稳定版</option>
            <option value="dynamic">一版 · B 动态版</option>
            <option value="both">两版 · A + B</option>
          </select>
          <small>直接影响生成次数与积分消耗</small>
        </label>
      </div>
    </section>
    <PersonalPromptConfirmationSetting />
    <BrowserNotificationSetting
      enabled={browserNotificationsEnabled}
      permission={browserNotificationPermission}
      onEnable={onEnableBrowserNotifications}
      onDisable={onDisableBrowserNotifications}
    />
  </div>
}

function UserManagement({ adminId, sharedAuthentication }: { adminId: string; sharedAuthentication: boolean }) {
  const [users, setUsers] = useState<AdminUser[]>([])
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [resetUserId, setResetUserId] = useState<string | null>(null)
  const [resetPassword, setResetPassword] = useState('')
  const [changeOpen, setChangeOpen] = useState(false)
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [newPasswordConfirmation, setNewPasswordConfirmation] = useState('')
  const [busy, setBusy] = useState<string | null>('load')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    setBusy('load')
    try {
      setUsers(await getAdminUsers(adminId))
      setError('')
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '无法读取账号列表')
    } finally {
      setBusy(null)
    }
  }, [adminId])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [load])

  const create = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const normalizedUsername = username.trim()
    if (!normalizedUsername || password.length < 12) return
    setBusy('create')
    setError('')
    setNotice('')
    try {
      const created = await createAdminUser(adminId, {
        username: normalizedUsername,
        password,
      })
      setUsers((current) => [...current, created].sort((left, right) => left.username.localeCompare(right.username, 'zh-CN')))
      setUsername('')
      setPassword('')
      setNotice(`账号“${created.username}”已创建，可以使用临时密码登录。`)
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '账号创建失败')
    } finally {
      setBusy(null)
    }
  }

  const reset = async (event: FormEvent<HTMLFormElement>, user: AdminUser) => {
    event.preventDefault()
    if (resetPassword.length < 12) return
    setBusy(`reset:${user.id}`)
    setError('')
    setNotice('')
    try {
      await resetAdminUserPassword(adminId, user.id, resetPassword)
      setResetUserId(null)
      setResetPassword('')
      setNotice(`账号“${user.username}”的密码已重置，旧登录会话已失效。`)
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '密码重置失败')
    } finally {
      setBusy(null)
    }
  }

  const changeOwnPassword = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (newPassword.length < 12 || newPassword !== newPasswordConfirmation) return
    setBusy('change-own-password')
    setError('')
    setNotice('')
    try {
      await changePassword(currentPassword, newPassword)
      setChangeOpen(false)
      setCurrentPassword('')
      setNewPassword('')
      setNewPasswordConfirmation('')
      setNotice('你的密码已修改，其他设备上的旧登录会话已退出。')
    } catch (cause) {
      if (cause instanceof ApiError && cause.code === 'CURRENT_PASSWORD_INVALID') setError('当前密码不正确，请重新输入。')
      else if (cause instanceof ApiError && cause.code === 'PASSWORD_UNCHANGED') setError('新密码不能与当前密码相同。')
      else setError(cause instanceof ApiError ? cause.message : '密码修改失败')
    } finally {
      setBusy(null)
    }
  }

  const deactivate = async (user: AdminUser) => {
    if (!window.confirm(`停用账号“${user.username}”后，该账号会立即退出且无法继续登录。确定停用吗？`)) return
    setBusy(`deactivate:${user.id}`)
    setError('')
    setNotice('')
    try {
      await deactivateAdminUser(adminId, user.id)
      setUsers((current) => current.map((item) => item.id === user.id ? { ...item, isActive: false } : item))
      setNotice(`账号“${user.username}”已停用。`)
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '账号停用失败')
    } finally {
      setBusy(null)
    }
  }

  const roleLabels: Record<AdminUser['role'], string> = {
    ADMIN: '管理员',
    OPERATOR: '运营人员',
    USER: '普通用户',
  }

  return <section className="settings-section account-management-section">
    <div className="settings-section-heading">
      <div><span>访问控制</span><h2>成员账号</h2><p>为局域网成员创建独立登录账号。新账号默认为普通用户，不能进入管理中心。</p></div>
      <button className="secondary-button" type="button" disabled={busy !== null} onClick={() => void load()}><RefreshCw className={busy === 'load' ? 'spin' : ''} size={16} />刷新列表</button>
    </div>
    <form className="account-create-form" onSubmit={(event) => void create(event)}>
      <label htmlFor="new-account-username"><span>登录账号</span><input id="new-account-username" name="username" value={username} onChange={(event) => setUsername(event.target.value)} minLength={1} maxLength={80} autoComplete="off" spellCheck={false} placeholder="例如：designer-01" required /><small>不能包含空格，创建后不可修改</small></label>
      <label htmlFor="new-account-password"><span>临时密码</span><input id="new-account-password" name="new-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={12} maxLength={512} autoComplete="new-password" placeholder="至少 12 个字符" required /><small>请通过可信方式交给成员</small></label>
      <button className="primary-button" type="submit" disabled={busy !== null || !username.trim() || password.length < 12}>{busy === 'create' ? <LoaderCircle className="spin" size={16} /> : <Plus size={16} />}{busy === 'create' ? '正在创建…' : '创建账号'}</button>
    </form>
    <div className="account-feedback" aria-live="polite">
      {notice ? <p><CheckCircle2 size={15} />{notice}</p> : null}
      {error ? <div className="inline-alert inline-alert--danger" role="alert"><AlertTriangle size={16} />{error}</div> : null}
    </div>
    <div className="account-list" aria-busy={busy === 'load'}>
      {users.map((user) => <article className={`account-row${user.isActive ? '' : ' is-inactive'}`} key={user.id}>
        <span className="account-avatar" aria-hidden="true"><UserRound size={18} /></span>
        <div className="account-identity"><strong>{user.username}</strong><span>{roleLabels[user.role]} · 创建于 {formatTime(user.createdAt)}</span></div>
        <span className={`account-state${user.isActive ? ' is-active' : ''}`}>{user.isActive ? '正常' : '已停用'}</span>
        {user.id === adminId && user.isActive && sharedAuthentication ? <div className="account-actions">
          <button className="secondary-button" type="button" disabled={busy !== null} onClick={() => { setChangeOpen(true); setResetUserId(null); setCurrentPassword(''); setNewPassword(''); setNewPasswordConfirmation(''); setNotice(''); setError('') }}><KeyRound size={15} />修改密码</button>
        </div> : null}
        {user.role === 'USER' && user.isActive ? <div className="account-actions">
          <button className="secondary-button" type="button" disabled={busy !== null} onClick={() => { setResetUserId(user.id); setResetPassword(''); setNotice(''); setError('') }}><KeyRound size={15} />重置密码</button>
          <button className="danger-button" type="button" disabled={busy !== null} onClick={() => void deactivate(user)}>{busy === `deactivate:${user.id}` ? <LoaderCircle className="spin" size={15} /> : <LogOut size={15} />}停用</button>
        </div> : null}
        {resetUserId === user.id ? <form className="account-reset-form" onSubmit={(event) => void reset(event, user)}>
          <label htmlFor={`reset-password-${user.id}`}><span>为“{user.username}”设置新密码</span><input id={`reset-password-${user.id}`} type="password" value={resetPassword} onChange={(event) => setResetPassword(event.target.value)} minLength={12} maxLength={512} autoComplete="new-password" placeholder="至少 12 个字符" required /></label>
          <div><button className="secondary-button" type="button" disabled={busy !== null} onClick={() => { setResetUserId(null); setResetPassword('') }}>取消</button><button className="primary-button" type="submit" disabled={busy !== null || resetPassword.length < 12}>{busy === `reset:${user.id}` ? <LoaderCircle className="spin" size={15} /> : <KeyRound size={15} />}确认重置</button></div>
        </form> : null}
        {user.id === adminId && changeOpen ? <form className="account-reset-form account-change-password-form" onSubmit={(event) => void changeOwnPassword(event)}>
          <label htmlFor="current-account-password"><span>当前密码</span><input id="current-account-password" type="password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} maxLength={512} autoComplete="current-password" required /></label>
          <label htmlFor="new-account-password-self"><span>新密码</span><input id="new-account-password-self" type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} minLength={12} maxLength={512} autoComplete="new-password" placeholder="至少 12 个字符" required /></label>
          <label htmlFor="confirm-account-password-self"><span>确认新密码</span><input id="confirm-account-password-self" type="password" value={newPasswordConfirmation} onChange={(event) => setNewPasswordConfirmation(event.target.value)} minLength={12} maxLength={512} autoComplete="new-password" aria-invalid={Boolean(newPasswordConfirmation && newPassword !== newPasswordConfirmation)} required /></label>
          <div><button className="secondary-button" type="button" disabled={busy !== null} onClick={() => { setChangeOpen(false); setCurrentPassword(''); setNewPassword(''); setNewPasswordConfirmation('') }}>取消</button><button className="primary-button" type="submit" disabled={busy !== null || !currentPassword || newPassword.length < 12 || newPassword !== newPasswordConfirmation}>{busy === 'change-own-password' ? <LoaderCircle className="spin" size={15} /> : <KeyRound size={15} />}保存新密码</button></div>
        </form> : null}
      </article>)}
      {!users.length && busy !== 'load' ? <EmptyState icon={<UserRound size={24} />} title="还没有成员账号" description="创建第一个普通用户账号后，对方即可从登录页进入。" /> : null}
      {busy === 'load' ? <div className="account-loading"><LoaderCircle className="spin" size={20} />正在读取成员账号…</div> : null}
    </div>
  </section>
}

function AdminCenterView({
  system,
  actor,
  section,
  onSectionChange,
  onKlingChanged,
}: {
  system: SystemStatus | null
  actor: AuthUser | null
  section: AdminSection
  onSectionChange: (section: AdminSection) => void
  onKlingChanged: () => Promise<void>
}) {
  const isAdmin = actor?.role === 'ADMIN'
  const canOperate = isAdmin || actor?.role === 'OPERATOR'
  const sections: Array<{ value: AdminSection; label: string; description: string; icon: React.ReactNode }> = [
    { value: 'overview', label: '运行总览', description: '生产开关、队列与告警', icon: <Activity size={17} /> },
    ...(isAdmin ? [{ value: 'accounts' as const, label: '成员账号', description: '创建、重置与停用', icon: <UserRound size={17} /> }] : []),
    { value: 'providers', label: 'Provider 与账号', description: '生成通道和登录空间', icon: <Clapperboard size={17} /> },
    { value: 'security', label: '流程与凭据', description: '确认策略和服务密钥', icon: <KeyRound size={17} /> },
  ]
  if (!canOperate) return <div className="page-view"><EmptyState icon={<ShieldCheck size={24} />} title="没有管理中心权限" description="请联系管理员为当前账号分配运营或管理员角色。" /></div>
  return <div className="page-view admin-view">
    <div className="page-title">
      <div><span>Production Control</span><h1>管理中心</h1><p>集中管理运行状态、生成通道与生产安全边界。</p></div>
      <div className={`system-health ${system ? 'is-online' : 'is-warning'}`}><span /><div><strong>{system ? '生产服务在线' : '正在读取服务状态'}</strong><small>{isAdmin ? '管理员权限' : '运营权限'}</small></div></div>
    </div>
    <nav className="subnav-tabs" aria-label="管理中心导航">
      {sections.map((item) => <button key={item.value} className={section === item.value ? 'is-active' : ''} onClick={() => onSectionChange(item.value)} aria-current={section === item.value ? 'page' : undefined}>
        <span>{item.icon}</span><span><strong>{item.label}</strong><small>{item.description}</small></span><ChevronRight size={16} />
      </button>)}
    </nav>
    <div className="admin-section-content" key={section}>
      {section === 'overview' ? <>
        <section className="admin-summary-grid" aria-label="系统摘要">
          <div><span className="summary-icon summary-icon--blue"><LayoutDashboard size={19} /></span><span><small>运行环境</small><strong>{system?.libtvAdapter === 'live' ? '正式生产' : '测试环境'}</strong></span></div>
          <div><span className="summary-icon summary-icon--green"><Activity size={19} /></span><span><small>LibTV 服务</small><strong>{system?.libtvAdapter === 'live' ? '已连接' : '模拟适配器'}</strong></span></div>
          <div><span className={`summary-icon ${system?.kling.available && system?.kling.authenticated ? 'summary-icon--green' : 'summary-icon--amber'}`}><Clapperboard size={19} /></span><span><small>Kling Provider</small><strong>{system?.kling.available && system?.kling.authenticated ? '已就绪' : '需要检查'}</strong></span></div>
        </section>
        <section className="settings-section admin-operations-card"><OperationsPanel adminId={actor?.userId ?? null} /></section>
      </> : null}
      {section === 'accounts' && isAdmin ? <UserManagement adminId={actor!.userId} sharedAuthentication={system?.sharedAuthentication ?? false} /> : null}
      {section === 'providers' ? isAdmin ? <>
        <KlingCliSettings adminId={actor!.userId} onChanged={onKlingChanged} />
        <LibTVAccountSettings adminId={actor!.userId} />
      </> : <EmptyState icon={<ShieldCheck size={24} />} title="需要管理员权限" description="Provider 登录和账号空间仅允许管理员修改。" /> : null}
      {section === 'security' ? <>
        <PromptConfirmationSetting adminId={actor!.userId} />
        {isAdmin ? <ProviderCredentials adminId={actor!.userId} /> : <EmptyState icon={<KeyRound size={24} />} title="凭据由管理员维护" description="你仍可管理生产确认流程，但不能查看或修改服务凭据。" />}
      </> : null}
    </div>
  </div>
}

function PromptConfirmationSetting({ adminId }: { adminId: string }) {
  const [runtime, setRuntime] = useState<{ version: number; promptConfirmationRequired: boolean } | null>(null)
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    setBusy(true)
    try {
      const snapshot = await getOperations(adminId)
      setRuntime({
        version: snapshot.runtime.version,
        promptConfirmationRequired: snapshot.runtime.config.promptConfirmationRequired !== false,
      })
      setError('')
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '无法读取提示词确认设置')
    } finally {
      setBusy(false)
    }
  }, [adminId])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [load])

  const toggle = async (automatic: boolean) => {
    if (!runtime) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const updated = await setPromptAutoConfirmation(adminId, runtime.version, automatic)
      setRuntime({
        version: updated.version,
        promptConfirmationRequired: updated.config.promptConfirmationRequired !== false,
      })
      setNotice(automatic
        ? '自动确认已开启，普通方案分析完成后将直接进入生成。'
        : '自动确认已关闭，后续方案需要人工确认后才会生成。')
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '提示词确认设置保存失败')
      await load()
    } finally {
      setBusy(false)
    }
  }

  const automatic = runtime?.promptConfirmationRequired === false
  return <section className="settings-section prompt-confirmation-section">
    <div className="settings-section-heading">
      <div><span>生成流程</span><h2>自动确认提示词</h2><p>{automatic ? '普通方案分析完成后将跳过人工确认，直接进入生成流程。需要质量复核或被系统拦截的方案仍需人工处理。' : '默认关闭。方案分析完成后，需要人工检查并确认提示词才会开始生成。'}</p></div>
      <div className="prompt-confirmation-control">
        <span className={`prompt-confirmation-state${automatic ? ' is-active' : ''}`}>{busy && !runtime ? '读取中' : automatic ? '已开启' : '已关闭'}</span>
        <label className="settings-switch" title="自动确认提示词">
          <input type="checkbox" checked={automatic} disabled={busy || !runtime} aria-label="自动确认提示词" onChange={(event) => void toggle(event.target.checked)} />
          <span aria-hidden="true" />
        </label>
      </div>
    </div>
    <div className="prompt-confirmation-feedback" aria-live="polite">
      {notice ? <p><CheckCircle2 size={15} />{notice}</p> : null}
      {error ? <div className="inline-alert inline-alert--danger" role="alert"><AlertTriangle size={16} />{error}</div> : null}
    </div>
  </section>
}

function App() {
  const [tasks, setTasks] = useState<Task[]>([])
  const [system, setSystem] = useState<SystemStatus | null>(null)
  const [actor, setActor] = useState<AuthUser | null>(null)
  const [devActorRole, setDevActorRole] = useState<'user' | 'admin'>(() => localStorage.getItem('development-actor-role') === 'admin' ? 'admin' : 'user')
  const [view, setView] = useState<View>(() => readAppLocation().view)
  const [detailId, setDetailId] = useState<string | null>(() => readAppLocation().detailId)
  const [adminSection, setAdminSection] = useState<AdminSection>(() => readAppLocation().adminSection)
  const [video, setVideo] = useState<{ artifactId: string; title: string } | null>(null)
  const [seed, setSeed] = useState<RemixSeed | null>(null)
  const [loading, setLoading] = useState(true)
  const [authRequired, setAuthRequired] = useState(false)
  const [remixStage, setRemixStage] = useState<'materials' | 'reuse' | null>(null)
  const [error, setError] = useState('')
  const [sidebarInfo, setSidebarInfo] = useState<'account' | 'help' | null>(null)
  const [nextTaskCursor, setNextTaskCursor] = useState<string | null>(null)
  const [loadingMoreTasks, setLoadingMoreTasks] = useState(false)
  const [browserNotificationsEnabled, setBrowserNotificationsEnabled] = useState(readBrowserNotificationPreference)
  const [notificationPermission, setNotificationPermission] = useState(browserNotificationPermission)
  const [notificationPromptDismissed, setNotificationPromptDismissed] = useState(false)
  const previousTaskPhasesRef = useRef<Map<string, string>>(new Map())
  const notificationBaselineReadyRef = useRef(false)
  const activeNotificationsRef = useRef<Map<string, Notification>>(new Map())

  const refreshTasks = useCallback(async () => {
    try {
      const page = await getTaskPage()
      setTasks((current) => {
        const recentIds = new Set(page.items.map((task) => task.id))
        return [...page.items, ...current.filter((task) => !recentIds.has(task.id))]
      })
      setNextTaskCursor(page.nextCursor)
      setAuthRequired(false)
      setError('')
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) {
        setActor(null)
        setTasks([])
        setAuthRequired(true)
        setError('')
      } else {
        setError(cause instanceof ApiError ? cause.message : '暂时无法连接生产服务')
      }
    }
  }, [])

  const refresh = useCallback(async () => {
    try {
      const status = await getSystemStatus()
      setSystem(status)
      setCsrfCookieName(status.csrfCookieName)
      if (!status.sharedAuthentication) {
        const developmentActorId = devActorRole === 'admin' ? status.phaseOneAdminId : status.phaseOneUserId
        setApiUserId(developmentActorId)
      } else {
        setApiUserId(null)
      }
      const [page, currentActor] = await Promise.all([getTaskPage(), getCurrentUser()])
      setActor(currentActor)
      setTasks(page.items)
      setNextTaskCursor(page.nextCursor)
      setAuthRequired(false)
      setError('')
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) {
        setActor(null)
        setTasks([])
        setAuthRequired(true)
        setError('')
      } else {
        setError(cause instanceof ApiError ? cause.message : '暂时无法连接生产服务')
      }
    } finally { setLoading(false) }
  }, [devActorRole])

  useEffect(() => {
    const initial = window.setTimeout(() => void refresh(), 0)
    return () => window.clearTimeout(initial)
  }, [refresh])

  useEffect(() => {
    if (!error || authRequired) return
    const retry = window.setInterval(() => void refresh(), 5000)
    return () => window.clearInterval(retry)
  }, [authRequired, error, refresh])

  useEffect(() => {
    const restoreLocation = () => {
      const next = readAppLocation()
      setView(next.view)
      setDetailId(next.detailId)
      setAdminSection(next.adminSection)
    }
    window.addEventListener('popstate', restoreLocation)
    return () => window.removeEventListener('popstate', restoreLocation)
  }, [])

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

  useEffect(() => {
    if (!actor) return
    let active = true
    let timer: number | undefined
    let inFlight = false
    const hasActiveTasks = tasks.some((task) => ACTIVE_PHASES.has(task.phase))
    const interval = detailId ? 30000 : hasActiveTasks ? 10000 : 30000
    const poll = async () => {
      if (!active || inFlight) {
        if (active) timer = window.setTimeout(() => void poll(), interval)
        return
      }
      inFlight = true
      try {
        await refreshTasks()
      } finally {
        inFlight = false
        if (active) timer = window.setTimeout(() => void poll(), interval)
      }
    }
    timer = window.setTimeout(() => void poll(), interval)
    return () => {
      active = false
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [actor, detailId, refreshTasks, tasks])

  useEffect(() => {
    const selected = tasks.find((task) => task.id === detailId)
    if (!detailId || !selected || !ACTIVE_PHASES.has(selected.phase)) return
    let active = true
    let timer: number | undefined
    const poll = async () => {
      if (!active) {
        if (active) timer = window.setTimeout(() => void poll(), 4000)
        return
      }
      try {
        const changed = await getTask(detailId)
        setTasks((current) => current.map((task) => task.id === changed.id ? changed : task))
      } catch {
        // The slower task-list refresh remains the fallback.
      } finally {
        if (active) timer = window.setTimeout(() => void poll(), 4000)
      }
    }
    timer = window.setTimeout(() => void poll(), 4000)
    return () => {
      active = false
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [detailId, tasks])

  const navigate = useCallback((nextView: View, nextDetailId: string | null = null, replace = false, nextAdminSection: AdminSection = 'overview') => {
    setView(nextView)
    setDetailId(nextView === 'make' ? nextDetailId : null)
    if (nextView === 'admin') setAdminSection(nextAdminSection)
    const params = new URLSearchParams()
    if (nextView !== 'make') params.set('view', nextView)
    if (nextView === 'make' && nextDetailId) params.set('task', nextDetailId)
    if (nextView === 'admin' && nextAdminSection !== 'overview') params.set('section', nextAdminSection)
    const url = `${window.location.pathname}${params.size ? `?${params.toString()}` : ''}`
    window.history[replace ? 'replaceState' : 'pushState'](null, '', url)
  }, [])

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
    for (const [taskId, notification] of activeNotificationsRef.current) {
      const phase = nextPhases.get(taskId)
      if (shouldCloseTaskNotification(phase, taskId === detailId)) {
        notification.close()
        activeNotificationsRef.current.delete(taskId)
      }
    }
    const pageIsInBackground = document.hidden || !document.hasFocus()
    if (browserNotificationsEnabled && notificationPermission === 'granted' && pageIsInBackground) {
      for (const task of tasks) {
        const payload = taskNotificationForTransition(previousPhases.get(task.id), task)
        if (!payload) continue
        activeNotificationsRef.current.get(task.id)?.close()
        const notification = new Notification(payload.title, {
          body: payload.body,
          tag: payload.tag,
          icon: '/favicon.svg',
        })
        activeNotificationsRef.current.set(task.id, notification)
        notification.onclose = () => {
          if (activeNotificationsRef.current.get(task.id) === notification) {
            activeNotificationsRef.current.delete(task.id)
          }
        }
        notification.onclick = () => {
          notification.close()
          activeNotificationsRef.current.delete(task.id)
          window.focus()
          navigate('make', task.id)
        }
      }
    }
    previousTaskPhasesRef.current = nextPhases
  }, [actor, browserNotificationsEnabled, detailId, navigate, notificationPermission, tasks])

  useEffect(() => {
    if (!detailId) return
    const closeSelectedNotification = () => {
      if (document.hidden || !document.hasFocus()) return
      activeNotificationsRef.current.get(detailId)?.close()
      activeNotificationsRef.current.delete(detailId)
    }
    closeSelectedNotification()
    window.addEventListener('focus', closeSelectedNotification)
    document.addEventListener('visibilitychange', closeSelectedNotification)
    return () => {
      window.removeEventListener('focus', closeSelectedNotification)
      document.removeEventListener('visibilitychange', closeSelectedNotification)
    }
  }, [detailId])

  const selectedTask = tasks.find((task) => task.id === detailId) ?? null
  const counts = useMemo(() => ({
    attention: tasks.filter((task) => task.phase === 'AWAITING_CONFIRMATION').length,
    active: tasks.filter((task) => ACTIVE_PHASES.has(task.phase)).length,
  }), [tasks])
  const showNotificationPrompt = browserNotificationsEnabled
    && notificationPermission === 'default'
    && !notificationPromptDismissed
    && tasks.some((task) => ACTIVE_PHASES.has(task.phase) || task.phase === 'AWAITING_CONFIRMATION')

  const taskChanged = useCallback(async () => {
    if (detailId) {
      try {
        const changed = await getTask(detailId)
        setTasks((current) => current.map((task) => task.id === changed.id ? changed : task))
        return
      } catch { /* Polling refresh below is the fallback. */ }
    }
    await refreshTasks()
  }, [detailId, refreshTasks])

  const loadMoreTasks = useCallback(async () => {
    if (!nextTaskCursor || loadingMoreTasks) return
    setLoadingMoreTasks(true)
    try {
      const page = await getTaskPage(nextTaskCursor)
      setTasks((current) => {
        const existingIds = new Set(current.map((task) => task.id))
        return [...current, ...page.items.filter((task) => !existingIds.has(task.id))]
      })
      setNextTaskCursor(page.nextCursor)
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '无法加载更早记录')
    } finally {
      setLoadingMoreTasks(false)
    }
  }, [loadingMoreTasks, nextTaskCursor])

  const remix = async (task: Task) => {
    setRemixStage('materials')
    try {
      const assets = [...task.assets].sort((a, b) => a.order - b.order)
      const loaded = await Promise.all(assets.map(async (asset) => ({ asset, file: await fetchAssetFile(asset.thumbnailUrl, asset.originalFilename) })))
      setSeed({
        id: createUuid(),
        storyboards: loaded.filter(({ asset }) => asset.role !== 'PRODUCT' && asset.usedForGeneration !== false).map(({ file }) => file),
        products: loaded.filter(({ asset }) => asset.role === 'PRODUCT' || asset.usedForGeneration === false).map(({ file }) => file),
        requirement: '',
      })
      navigate('make')
    } catch (cause) { setError(cause instanceof Error ? cause.message : '无法加载原素材') } finally { setRemixStage(null) }
  }
  const reuseCompleted = async (task: Task, variants: VariantKind[]) => {
    if (!variants.length) return
    setRemixStage('reuse')
    setError('')
    try {
      const reused = await reuseTask(task, variants)
      setTasks((current) => [reused, ...current.filter((item) => item.id !== reused.id)])
      navigate('make', reused.id)
      try {
        const confirmed = await confirmTask(reused)
        setTasks((current) => current.map((item) => item.id === confirmed.id ? confirmed : item))
      } catch (cause) {
        try {
          const changed = await getTask(reused.id)
          setTasks((current) => current.map((item) => item.id === changed.id ? changed : item))
        } catch { /* The global task poll remains the fallback. */ }
        throw cause
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '一键复用失败，请稍后重试')
    } finally {
      setRemixStage(null)
    }
  }
  const play = (task: Task, variant: Variant) => {
    if (!variant.downloadArtifactId) { navigate('make', task.id); return }
    setVideo({ artifactId: variant.downloadArtifactId, title: `${task.title} · ${variant.kind === 'STABLE' ? 'A 稳定展示' : 'B 动态广告'}` })
  }
  const created = useCallback((task: Task, open = false) => {
    setTasks((current) => [task, ...current.filter((item) => item.id !== task.id)])
    setSeed(null)
    if (open) navigate('make', task.id)
  }, [navigate])
  const feedbackChanged = useCallback((changed: Task) => {
    setTasks((current) => current.map((task) => task.id === changed.id ? changed : task))
  }, [])
  const switchView = (next: View) => { navigate(next); window.scrollTo({ top: 0, behavior: 'smooth' }) }
  const switchDevelopmentActor = () => {
    const next = devActorRole === 'admin' ? 'user' : 'admin'
    localStorage.setItem('development-actor-role', next)
    setDevActorRole(next)
    setSidebarInfo(null)
    setLoading(true)
  }
  const signOut = async () => {
    try { await logout() } catch { /* Local state still returns to the login boundary. */ }
    setActor(null)
    setTasks([])
    setSidebarInfo(null)
    setAuthRequired(true)
  }

  const canOperate = actor?.role === 'ADMIN' || actor?.role === 'OPERATOR'
  const nav: Array<{ value: View; label: string; icon: React.ReactNode; badge?: number }> = [
    { value: 'make', label: '制作', icon: <Plus size={18} /> },
    { value: 'records', label: '任务', icon: <ListVideo size={18} />, badge: counts.attention || counts.active },
    ...(canOperate ? [{ value: 'admin' as const, label: '管理', icon: <ShieldCheck size={18} /> }] : []),
    { value: 'settings', label: '设置', icon: <Settings size={18} /> },
  ]
  if (system?.sharedAuthentication && authRequired) {
    return <LoginScreen onAuthenticated={async () => { setLoading(true); await refresh() }} />
  }
  return <div className="app-shell">
    <a className="skip-link" href="#main-content">跳到主要内容</a>
    <aside className="sidebar">
      <ProductLogo />
      <nav className="sidebar-main-nav" aria-label="主导航">{nav.filter((item) => item.value !== 'settings').map((item) => <button key={item.value} onClick={() => switchView(item.value)} className={view === item.value ? 'is-active' : ''}>{item.icon}<span>{item.label}</span>{item.badge ? <i>{item.badge}</i> : null}</button>)}</nav>
      <div className="sidebar-bottom">
        <div className="sidebar-status"><span className={error ? 'is-offline' : ''} /><span>{error ? '服务连接异常' : system?.environment === 'test' ? '测试版' : '正式版'}</span></div>
        <button className={`sidebar-settings ${view === 'settings' ? 'is-active' : ''}`} onClick={() => switchView('settings')}><Settings size={18} /><span>设置</span></button>
        <div className="sidebar-utility"><button onClick={() => setSidebarInfo((current) => current === 'help' ? null : 'help')} aria-label="帮助" title="帮助"><HelpCircle size={17} /></button><button onClick={() => setSidebarInfo((current) => current === 'account' ? null : 'account')} aria-label="账号" title="账号"><UserRound size={17} /></button></div>
        {sidebarInfo ? <div className="sidebar-popover" role="status"><strong>{sidebarInfo === 'help' ? '制作帮助' : '当前账号'}</strong><p>{sidebarInfo === 'help' ? '上传服装与参考图后，确认方案即可开始生成。历史视频可在记录中继续处理。' : `${actor?.username ?? '生产账号'} · ${actor?.role === 'ADMIN' ? '管理员' : actor?.role === 'OPERATOR' ? '运营人员' : '普通用户'}`}</p>{sidebarInfo === 'account' && system?.sharedAuthentication ? <button onClick={() => void signOut()}>退出登录</button> : sidebarInfo === 'account' && system?.phaseOneAdminId ? <button onClick={switchDevelopmentActor}>切换为{devActorRole === 'admin' ? '普通用户' : '管理员'}</button> : <button onClick={() => setSidebarInfo(null)}>关闭</button>}</div> : null}
      </div>
    </aside>
    <div className="app-body">
      <header className="mobile-topbar"><ProductLogo /><div className="service-state"><span className={error ? 'is-offline' : ''} />{error ? '服务异常' : system?.environment === 'test' ? '测试版' : '正式版'}</div></header>
      <main id="main-content">{loading ? <div className="page-loading"><LoaderCircle className="spin" size={26} /><strong>正在加载生产任务</strong></div> : <>
      {error ? <div className="service-banner"><AlertTriangle size={18} /><span>{error}</span><button onClick={() => void refresh()}><RefreshCw size={15} />重新连接</button></div> : null}
      {showNotificationPrompt ? <div className="notification-permission-banner" role="region" aria-label="浏览器通知">
        <Bell size={18} />
        <span><strong>后台进度提醒</strong><small>开启通知，方案待确认或视频完成时会及时提醒你。</small></span>
        <button className="secondary-button" type="button" onClick={() => void enableBrowserNotifications()}>开启通知</button>
        <button className="icon-button" type="button" aria-label="暂不开启通知" title="暂不开启" onClick={() => setNotificationPromptDismissed(true)}><X size={17} /></button>
      </div> : null}
      {view === 'make' && !selectedTask ? <HomeView tasks={tasks} seed={seed} system={system} onCreated={created} onOpen={(task) => navigate('make', task.id)} onView={switchView} onPlay={play} onRemix={(task) => void remix(task)} onFeedbackChanged={feedbackChanged} /> : null}
      {view === 'make' && selectedTask ? <ProductionWorkspace key={`${selectedTask.id}-${selectedTask.phase}`} task={selectedTask} onClose={() => navigate('make')} onChanged={taskChanged} onRemix={() => void remix(selectedTask)} onReuse={(variants) => void reuseCompleted(selectedTask, variants)} onPlay={(variant) => play(selectedTask, variant)} /> : null}
      {view === 'records' ? <RecordsView tasks={tasks} hasMore={Boolean(nextTaskCursor)} loadingMore={loadingMoreTasks} onLoadMore={() => void loadMoreTasks()} onOpen={(task) => navigate('make', task.id)} onPlay={play} onRemix={(task) => void remix(task)} onFeedbackChanged={feedbackChanged} /> : null}
      {view === 'admin' ? <AdminCenterView system={system} actor={actor} section={adminSection} onSectionChange={(section) => navigate('admin', null, false, section)} onKlingChanged={refresh} /> : null}
      {view === 'settings' ? <SettingsView
        system={system}
        onLogout={() => void signOut()}
        browserNotificationsEnabled={browserNotificationsEnabled}
        browserNotificationPermission={notificationPermission}
        onEnableBrowserNotifications={enableBrowserNotifications}
        onDisableBrowserNotifications={disableBrowserNotifications}
      /> : null}
      </>}</main>
    </div>
    <nav className="mobile-nav" aria-label="移动端主导航" style={{ gridTemplateColumns: `repeat(${nav.length}, minmax(0, 1fr))` }}>{nav.map((item) => <button key={item.value} onClick={() => switchView(item.value)} className={view === item.value ? 'is-active' : ''}>{item.icon}<span>{item.label}</span>{item.badge ? <i>{item.badge}</i> : null}</button>)}</nav>
    {video ? <VideoPreview artifactId={video.artifactId} title={video.title} onClose={() => setVideo(null)} /> : null}
    {remixStage ? <div className="global-loading"><LoaderCircle className="spin" size={20} /><span>{remixStage === 'reuse' ? '正在复用素材和提示词并提交生成' : '正在加载原素材'}</span></div> : null}
  </div>
}

export default App
