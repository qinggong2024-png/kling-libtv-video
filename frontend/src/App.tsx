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
  Images,
  KeyRound,
  LayoutDashboard,
  Library,
  ListVideo,
  LoaderCircle,
  LogIn,
  LogOut,
  LockKeyhole,
  MoreHorizontal,
  Package,
  Pencil,
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
import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { createPortal } from 'react-dom'
import {
  ApiError,
  analyzeTask,
  cancelTask,
  changePassword,
  confirmTask,
  createAdminUser,
  createVideoTask,
  deactivateAdminUser,
  fetchArtifactObjectUrl,
  fetchAssetFile,
  fetchAssetObjectUrl,
  fetchImageAssetFile,
  getSystemStatus,
  getCurrentUser,
  getMotionActions,
  getTaskPage,
  getTask,
  getSiteStyleProfiles,
  getVideoTemplates,
  restoreOutput,
  reuseTask,
  saveArtifact,
  setApiUserId,
  setCsrfCookieName,
  uploadStoryboard,
  getAdminCredentials,
  getAdminUsers,
  getBachConfig,
  getKlingConfig,
  getKlingElements,
  getKlingStatus,
  getWaveSpeedConfig,
  getOperations,
  getPersonalPromptAutoConfirmation,
  updateAdminCredentials,
  updateBachConfig,
  updateKlingConfig,
  refreshKlingCapabilities,
  updateWaveSpeedConfig,
  verifyWaveSpeedConfig,
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
import type { AdminCredentialsStatus, AdminUser, AuthUser, BachConfig, FeedbackValue, KlingConfig, KlingElement, KlingStatus, MotionActionSummary, SiteStyleProfileSummary, StatusTone, SystemStatus, Task, Variant, VariantKind, VideoTemplateSummary, WaveSpeedConfig } from './types'
import { CustomPromptField } from './CustomPromptField'
import { ErrorBoundary } from './ErrorBoundary'
import { GenerationFeedbackPanel } from './GenerationFeedback'
import { ImageCenter } from './ImageCenter'
import type { ImageCenterNotificationEvent, ImageCenterVideoHandoff } from './ImageCenter'
import { KlingSubjectsLibrary } from './KlingSubjectsLibrary'
import { LoginFlowLines } from './LoginFlowLines'
import { OperationsPanel } from './OperationsPanel'
import { SubjectInputPanel } from './SubjectInputPanel'
import { IMAGE_FILE_ACCEPT, isSupportedImageFile } from './imageFiles'
import { groupBatchUploadFiles } from './batchUpload'
import type { BatchUploadGroup } from './batchUpload'
import {
  buildSubjectImageReferences,
  createEmptySubjectReferenceFiles,
  getSubjectReferenceCount,
  validateSubjectReferenceFiles,
} from './subjectFiles'
import type { SubjectInputMode, SubjectReferenceFiles } from './subjectFiles'
import { createWaveSpeedConfigDraft, normalizeWaveSpeedConfig } from './wavespeedConfig'
import type { WaveSpeedConfigDraft } from './wavespeedConfig'
import { formatRiskFlags } from './riskLabels'
import {
  formatDurationSeconds,
  formatElapsed,
  currentProductionStageIndex,
  parseTaskTimestamp,
  visibleProductionStageKeys,
  visibleTaskTimingStageKeys,
} from './taskTiming'
import { createUuid } from './uuid'
import {
  providerActionRequiredMessage,
  providerPresentation,
  providerProgress,
  providerTimingStageLabel,
  variantExecutionMessage,
} from './providerPresentation'
import {
  readBrowserNotificationPreference,
  shouldCloseTaskNotification,
  taskNotificationForTransition,
  writeBrowserNotificationPreference,
} from './browserNotifications'
import type { TaskNotification } from './browserNotifications'
import {
  buildKlingConfigPatch,
  createKlingConfigDraft,
  formatKlingApiVersion,
  klingApiStatusPresentation,
  KLING_BASE_URL_OPTIONS,
  KLING_ASPECT_RATIO_OPTIONS,
  KLING_AUDIO_OPTIONS,
  KLING_MODEL_OPTIONS,
  KLING_RESOLUTION_OPTIONS,
  validateKlingConfig,
} from './klingConfig'
import type { KlingConfigDraft } from './klingConfig'
import { CatalogEditor } from './CatalogEditor'
import { createImageCenterVideoSeed } from './imageCenterVideoSeed'
import { loadVideoComposerSettings, saveVideoComposerSettings } from './videoComposerSettings'
import {
  formatVideoDurationOptions,
  getVideoDurationOptions,
  normalizeVideoDuration,
} from './videoDurationOptions'

type View = 'images' | 'make' | 'records' | 'library' | 'admin' | 'settings'
type AdminSection = 'overview' | 'accounts' | 'providers' | 'security'
type UploadBucket = 'storyboard' | 'product'
type Material = { id: string; file: File }
type RemixSeed = { id: string; storyboards: File[]; products: File[]; subjectFiles?: SubjectReferenceFiles; requirement?: string }
type RecordFilter = 'all' | 'attention' | 'active' | 'partial' | 'done' | 'failed' | 'cancelled'
type InPageTaskToast = {
  id: string
  taskId: string
  view: 'images' | 'make'
  title: string
  body: string
  tone: 'success' | 'warning'
  expiresAt: number
}
type TaskNotificationEvent = {
  notificationKey: string
  taskId: string
  view: 'images' | 'make'
  payload: TaskNotification
  tone: InPageTaskToast['tone']
}

const UPLOAD_CONCURRENCY = 4
const DISMISSED_ATTENTION_STORAGE_KEY = 'dismissed-home-attention'
const DISMISSED_ATTENTION_ITEMS_STORAGE_KEY = 'dismissed-home-attention-items'

function browserNotificationPermission(): NotificationPermission | 'unsupported' {
  return 'Notification' in window ? Notification.permission : 'unsupported'
}

function taskPrompt(task: Task, kind: VariantKind): string {
  return task.variants.find((variant) => variant.kind === kind)?.promptText
    ?? task.variants[0]?.promptText
    ?? ''
}

function readAppLocation(): { view: View; detailId: string | null; adminSection: AdminSection } {
  const params = new URLSearchParams(window.location.search)
  const requestedView = params.get('view')
  const view: View = requestedView === 'images' || requestedView === 'records' || requestedView === 'library' || requestedView === 'admin' || requestedView === 'settings' ? requestedView : 'make'
  const requestedAdminSection = params.get('section')
  const adminSection: AdminSection = requestedAdminSection === 'accounts' || requestedAdminSection === 'providers' || requestedAdminSection === 'security'
    ? requestedAdminSection
    : 'overview'
  return { view, detailId: view === 'make' ? params.get('task') : null, adminSection }
}

async function imageCenterOutputFile(
  output: ImageCenterVideoHandoff['outputs'][number],
  outfitName: string,
  index: number,
): Promise<File> {
  if (output.file) return output.file
  if (!output.url) throw new Error(`“${outfitName}”的分镜 ${index + 1} 暂无可用图片文件。`)
  return fetchImageAssetFile(output.url, `${outfitName}-分镜-${index + 1}`)
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
  VALIDATING: '正在校验视频方案',
}

const statusMeta: Record<string, { label: string; tone: StatusTone }> = {
  DRAFT: { label: '正在上传素材', tone: 'neutral' },
  ANALYZING: { label: '正在分析图片', tone: 'active' },
  AWAITING_CONFIRMATION: { label: '等待确认方案', tone: 'warning' },
  PREPARING: { label: '正在准备生成', tone: 'active' },
  WAITING_FOR_SEAL: { label: '正在锁定生成任务', tone: 'active' },
  QUEUED: { label: '等待生成', tone: 'active' },
  GENERATING: { label: '正在生成视频', tone: 'active' },
  DOWNLOADING: { label: '正在下载成品', tone: 'active' },
  VALIDATING: { label: '正在校验成品', tone: 'active' },
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

function variantKindShortLabel(kind: VariantKind) {
  return kind === 'STABLE' ? '稳' : '动'
}

function variantKindDisplayName(kind: VariantKind) {
  return kind === 'STABLE' ? '稳定展示' : '动态广告'
}

function variantShortLabel(variant: Variant) {
  return variant.variantIndex ? String(variant.variantIndex) : variantKindShortLabel(variant.kind)
}

function variantDisplayName(variant: Variant) {
  return variant.variantIndex ? `结果 ${variant.variantIndex}` : variantKindDisplayName(variant.kind)
}

function variantLabelClass(variant: Variant) {
  return variant.variantIndex ? 'variant-label--result' : variant.kind === 'STABLE' ? 'variant-label--a' : 'variant-label--b'
}

function variantFileToken(variant: Variant) {
  return variant.variantKey ?? variant.kind.toLowerCase()
}

function variantErrorMessage(variant: Variant) {
  return variant.errorMessage ?? variant.providerErrorMessage ?? null
}

function variantErrorRetryable(variant: Variant) {
  return variant.retryable ?? variant.providerErrorRetryable ?? null
}

function variantErrorDetails(variant: Variant) {
  return variant.errorDetails ?? variant.providerErrorDetails ?? null
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

function InPageTaskToasts({
  toasts,
  onOpen,
  onDismiss,
}: {
  toasts: InPageTaskToast[]
  onOpen: (toast: InPageTaskToast) => void
  onDismiss: (id: string) => void
}) {
  if (!toasts.length) return null
  return <div className="task-toast-region" aria-live="polite" aria-label="任务提醒">
    {toasts.map((toast) => <section key={toast.id} className={`task-toast task-toast--${toast.tone}`} role="status">
      <span className="task-toast-icon" aria-hidden="true">
        {toast.tone === 'success' ? <CheckCircle2 size={19} /> : <CircleAlert size={19} />}
      </span>
      <button className="task-toast-content" type="button" onClick={() => onOpen(toast)}>
        <strong>{toast.title}</strong>
        <span>{toast.body}</span>
        <small>点击查看任务</small>
      </button>
      <button className="task-toast-dismiss" type="button" aria-label={`关闭“${toast.title}”提醒`} onClick={() => onDismiss(toast.id)}>
        <X size={17} />
      </button>
    </section>)}
  </div>
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

  const visibleStageKeys = new Set(visibleTaskTimingStageKeys(task.workflowKind))
  const stages = TASK_TIMING_STAGE_META.filter(({ key }) => visibleStageKeys.has(key)).map((meta) => ({
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
          {activeStage ? providerTimingStageLabel(activeStage.key, task.generationProvider) : taskStatus(task).label}
        </h3>
        {activeStage ? <p aria-live="polite">已进行 {formatDurationSeconds(stageElapsedSeconds(activeStage.stage, now) ?? 0)}</p> : null}
      </div>
      <dl className="task-timing-summary" aria-label="任务耗时汇总">
        <div><dt>系统处理</dt><dd>{systemSeconds > 0 ? formatDurationSeconds(systemSeconds) : '暂无记录'}</dd></div>
        <div><dt>等待确认</dt><dd>{confirmationSeconds > 0 ? formatDurationSeconds(confirmationSeconds) : '0 秒'}</dd></div>
        <div><dt>总耗时</dt><dd>{formatDurationSeconds(totalSeconds)}</dd></div>
      </dl>
    </header>
    <ol
      className="task-timing-stages"
      style={{ gridTemplateColumns: `repeat(${stages.length}, minmax(0, 1fr))` }}
    >
      {stages.map(({ key, category, stage }, index) => {
        const elapsed = stageElapsedSeconds(stage, now)
        const statusText = stage.status === 'ACTIVE'
          ? formatCompactDurationSeconds(elapsed ?? 0)
          : stage.status === 'COMPLETED'
            ? elapsed === null ? '已完成' : formatCompactDurationSeconds(elapsed)
            : stage.status === 'FAILED' ? '未完成' : '待执行'
        const fullLabel = providerTimingStageLabel(key, task.generationProvider)
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

function ProviderBadge({ provider }: { provider: string }) {
  const meta = providerPresentation(provider)
  return <span className={`provider-badge ${meta.cssClass}`}>{meta.displayLabel}</span>
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
    ANALYSIS_SCHEMA_INVALID: '分析结果不完整，无法生成可确认的视频方案。',
  }
  return messages[task.phaseReasonCode ?? '']
    ?? providerActionRequiredMessage(task.phaseReasonCode, task.generationProvider)
}

function TaskStatusBadge({ task }: { task: Task }) {
  const meta = taskStatus(task)
  return <span className={`status status--${meta.tone}`}><span />{meta.label}</span>
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

function ProductLogo({ subtitle = 'AI 视频生产' }: { subtitle?: string }) {
  return <span className="brand-lockup"><span className="brand-mark"><Clapperboard size={19} /></span><span><strong>衣影工坊</strong><small title={subtitle}>{subtitle}</small></span></span>
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
        <LoginFlowLines />
        <ProductLogo />
        <div className="login-brand-copy">
          <span>KLING API PRODUCTION</span>
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

const MATERIAL_DRAG_TYPE = 'application/x-kling-api-material'

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

function ProductionComposer({ seed, onCreated, system, actorId }: {
  seed: RemixSeed | null
  onCreated: (task: Task, open?: boolean) => void
  system: SystemStatus | null
  actorId: string | null
}) {
  const [storedSettings] = useState(() => loadVideoComposerSettings(localStorage))
  const [storyboards, setStoryboards] = useState<Material[]>(() => seed?.storyboards.map((file, index) => ({ id: createUuid(), file, sourceImageOutputId: seed.storyboardOutputIds?.[index] })) ?? [])
  const [batchGroups, setBatchGroups] = useState<BatchUploadGroup[]>([])
  const [templates, setTemplates] = useState<VideoTemplateSummary[]>([])
  const [profiles, setProfiles] = useState<SiteStyleProfileSummary[]>([])
  const [elements, setElements] = useState<KlingElement[]>([])
  const [templateId, setTemplateId] = useState(storedSettings.templateId)
  const [siteProfileId, setSiteProfileId] = useState(storedSettings.siteProfileId)
  const [generationMode, setGenerationMode] = useState<'automatic' | 'custom'>(() => seed?.requirement ? 'custom' : storedSettings.generationMode)
  const [customPrompt, setCustomPrompt] = useState(() => seed?.requirement ?? storedSettings.customPrompt)
  const [subjectMode, setSubjectMode] = useState<SubjectInputMode>(() => seed?.subjectFiles?.frontalImage ? 'upload' : 'none')
  const [subjectFiles, setSubjectFiles] = useState<SubjectReferenceFiles>(() => seed?.subjectFiles ?? createEmptySubjectReferenceFiles())
  const [elementId, setElementId] = useState('')
  const [resultCount, setResultCount] = useState(storedSettings.resultCount)
  const [durationSeconds, setDurationSeconds] = useState(storedSettings.durationSeconds)
  const [actionIntensity, setActionIntensity] = useState<'low' | 'standard' | 'high'>(storedSettings.actionIntensity)
  const [cutMode, setCutMode] = useState<'explicit_cuts' | 'continuous_when_possible'>(storedSettings.cutMode)
  const [catalogLoading, setCatalogLoading] = useState(true)
  const [catalogError, setCatalogError] = useState('')
  const [elementCatalogError, setElementCatalogError] = useState('')
  const [elementsLoading, setElementsLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [stage, setStage] = useState('正在上传素材')
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [submittedNotice, setSubmittedNotice] = useState('')
  const [resetting, setResetting] = useState(false)
  const [preview, setPreview] = useState<{ file: File; label: string } | null>(null)
  const storyboardInputRef = useRef<HTMLInputElement>(null)
  const batchInputRef = useRef<HTMLInputElement>(null)
  const resetTimerRef = useRef<number | null>(null)
  const uploadAbortRef = useRef<AbortController | null>(null)
  const videoGeneration = system?.videoGeneration ?? system?.kling
  const activeProvider = providerPresentation(videoGeneration?.provider)
  const activeModel = videoGeneration?.model || videoGeneration?.models[0] || activeProvider.displayName
  const referenceLimit = videoGeneration?.imageInputLimit ?? 0
  const storyboardLimit = Math.min(7, Math.max(1, referenceLimit || 7))
  const durationOptions = useMemo(
    () => getVideoDurationOptions(videoGeneration, storyboards.length),
    [storyboards.length, videoGeneration],
  )
  const normalizedDurationSeconds = normalizeVideoDuration(durationSeconds, durationOptions)
  const durationOptionsLabel = formatVideoDurationOptions(durationOptions)
  const providerAvailable = Boolean(videoGeneration?.available && videoGeneration.authenticated)
  const subjectValidation = validateSubjectReferenceFiles(subjectFiles)
  const subjectReferenceCount = getSubjectReferenceCount(subjectMode, subjectFiles, elementId)
  const subjectReady = subjectMode === 'none'
    || (subjectMode === 'upload' && subjectValidation.isValid)
    || (subjectMode === 'history' && Boolean(elementId))
  const providerInputsSupported = storyboards.length + subjectReferenceCount <= referenceLimit
  const selectedTemplate = templates.find((item) => item.id === templateId) ?? null
  const selectedProfile = profiles.find((item) => item.id === siteProfileId) ?? null
  const customPromptReady = generationMode !== 'custom' || Boolean(customPrompt.trim())
  const productionReady = selectedTemplate?.status === 'active'
    && (generationMode === 'custom' || selectedProfile?.status === 'active')
  const templateAcceptsCount = Boolean(selectedTemplate && storyboards.length >= selectedTemplate.minImages && storyboards.length <= selectedTemplate.maxImages)
  const formLocked = busy || resetting
  useEffect(() => {
    let active = true
    Promise.all([getVideoTemplates(), getSiteStyleProfiles()])
      .then(([nextTemplates, nextProfiles]) => {
        if (!active) return
        setTemplates(nextTemplates)
        setProfiles(nextProfiles)
        setTemplateId((current) => nextTemplates.some((item) => item.id === current) ? current : nextTemplates[0]?.id ?? '')
        setSiteProfileId((current) => nextProfiles.some((item) => item.id === current) ? current : nextProfiles[0]?.id ?? '')
        setCatalogError('')
      })
      .catch((cause) => {
        if (active) setCatalogError(cause instanceof Error ? cause.message : '模板与站点风格加载失败')
      })
      .finally(() => { if (active) setCatalogLoading(false) })
    return () => { active = false }
  }, [])
  useEffect(() => {
    saveVideoComposerSettings(localStorage, {
      templateId,
      siteProfileId,
      generationMode,
      customPrompt,
      resultCount,
      durationSeconds: normalizedDurationSeconds,
      actionIntensity,
      cutMode,
    })
  }, [actionIntensity, customPrompt, cutMode, generationMode, normalizedDurationSeconds, resultCount, siteProfileId, templateId])
  useEffect(() => {
    if (!system || (!system.sharedAuthentication && !actorId)) {
      return
    }
    const controller = new AbortController()
    void Promise.allSettled([
      getKlingElements(actorId, 1, 100, false, controller.signal),
      getKlingElements(actorId, 1, 100, true, controller.signal),
    ])
      .then((results) => {
        if (controller.signal.aborted) return
        const nextElements = new Map<string, KlingElement>()
        for (const result of results) {
          if (result.status !== 'fulfilled') continue
          for (const element of result.value.items) {
            if (!nextElements.has(element.id)) nextElements.set(element.id, element)
          }
        }
        setElements([...nextElements.values()])
        const failures = results
          .filter((result): result is PromiseRejectedResult => result.status === 'rejected')
          .map((result) => result.reason instanceof ApiError ? result.reason.message : '主体列表加载失败')
        setElementCatalogError(failures.join('；'))
      })
      .finally(() => {
        if (!controller.signal.aborted) setElementsLoading(false)
      })
    return () => controller.abort()
  }, [actorId, system])
  useEffect(() => () => {
    if (resetTimerRef.current !== null) window.clearTimeout(resetTimerRef.current)
    uploadAbortRef.current?.abort()
  }, [])
  const addFiles = (files: File[]) => {
    setSubmittedNotice('')
    const images = files.filter(isSupportedImageFile)
    const rejectedCount = files.length - images.length
    const accepted = images.slice(0, Math.max(0, storyboardLimit - storyboards.length)).map((file) => ({ id: createUuid(), file }))
    const notices: string[] = []
    if (rejectedCount) notices.push(`${rejectedCount} 个文件不是支持的 JPG、PNG 或 WEBP 图片`)
    if (images.length !== accepted.length) notices.push(`当前模型的分镜图最多添加 ${storyboardLimit} 张，超出部分未添加`)
    setNotice(notices.join('；'))
    setStoryboards((items) => [...items, ...accepted])
  }
  const addBatchFiles = (files: File[]) => {
    const result = groupBatchUploadFiles(files)
    setBatchGroups(result.groups)
    const valid = result.groups.filter((group) => !group.errors.length)
    if (valid.length) {
      const first = valid[0]
      setStoryboards(first.storyboards.map((file) => ({ id: createUuid(), file })))
      setSubjectMode('upload')
      setSubjectFiles({ frontalImage: first.productFront, backImage: first.productBack, detailImages: [] })
    }
    setNotice([
      valid.length ? `已识别 ${valid.length} 组素材，将批量创建 ${valid.length} 个任务` : '没有识别到完整素材组',
      result.rejected.length ? `${result.rejected.length} 个文件未匹配命名规则` : '',
      ...result.groups.filter((group) => group.errors.length).map((group) => `${group.key}：${group.errors.join('、')}`),
    ].filter(Boolean).join('；'))
  }
  const dropAt = (event: React.DragEvent, target: number) => {
    event.preventDefault()
    event.stopPropagation()
    const id = event.dataTransfer.getData(MATERIAL_DRAG_TYPE)
    const sourceBucket = event.dataTransfer.getData('text/material-bucket') as UploadBucket
    if (!id || sourceBucket !== 'storyboard') return
    setStoryboards((current) => {
      const next = [...current]
      const currentSourceIndex = next.findIndex((value) => value.id === id)
      if (currentSourceIndex < 0) return current
      const [moved] = next.splice(currentSourceIndex, 1)
      next.splice(Math.min(target, next.length), 0, moved)
      return next
    })
  }
  const remove = (id: string) => setStoryboards((items) => items.filter((item) => item.id !== id))
  const handleDrop = (event: React.DragEvent, target: number) => {
    if (event.dataTransfer.types.includes(MATERIAL_DRAG_TYPE)) {
      dropAt(event, target)
      return
    }
    if (!event.dataTransfer.files.length) return
    event.preventDefault()
    event.stopPropagation()
    addFiles(Array.from(event.dataTransfer.files))
  }
  const submit = async () => {
    if (!storyboards.length || !providerAvailable || !subjectReady || !providerInputsSupported || !productionReady || !templateAcceptsCount || !customPromptReady) return
    setBusy(true)
    setError('')
    setNotice('')
    setSubmittedNotice('')
    const uploadController = new AbortController()
    uploadAbortRef.current?.abort()
    uploadAbortRef.current = uploadController
    let uploadFailure: unknown
    try {
      const uploadStartedAt = performance.now()
      let completedUploads = 0
      const validBatchGroups = batchGroups.filter((group) => !group.errors.length)
      const subjectReferences = subjectMode === 'upload' ? buildSubjectImageReferences(subjectFiles) : []
      const submissionGroups = validBatchGroups.length
        ? validBatchGroups
        : [{ key: storyboards[0]?.file.name.replace(/\.[^.]+$/, '') || 'video', productFront: subjectMode === 'upload' ? subjectFiles.frontalImage : null, productBack: subjectMode === 'upload' ? subjectFiles.backImage : null, storyboards: storyboards.map((item) => item.file), errors: [] }]
      const uploadCount = submissionGroups.reduce((total, group) => total + group.storyboards.length + (group.productFront ? 1 : 0) + (group.productBack ? 1 : 0), 0)
      const uploadOne = async (file: File, label: string, sourceImageOutputId?: string) => {
        try {
          const uploaded = await uploadStoryboard(file, uploadController.signal)
          completedUploads += 1
          setStage(`正在上传${label} ${completedUploads}/${uploadCount}`)
          setProgress(Math.round((completedUploads / uploadCount) * 52))
          return uploaded
        } catch (cause) {
          if (uploadFailure === undefined) {
            uploadFailure = cause
            uploadController.abort(cause)
          }
          throw cause
        }
      }
      let firstTask: Task | null = null
      for (const [groupIndex, group] of submissionGroups.entries()) {
        const [uploads, subjectUploads] = await Promise.all([
          mapWithConcurrency(group.storyboards, UPLOAD_CONCURRENCY, (file) => uploadOne(file, '分镜与主体素材')),
          validBatchGroups.length
            ? mapWithConcurrency([group.productFront, group.productBack].filter((file): file is File => Boolean(file)), UPLOAD_CONCURRENCY, (file) => uploadOne(file, '分镜与主体素材'))
            : mapWithConcurrency(subjectReferences, UPLOAD_CONCURRENCY, (reference) => uploadOne(reference.file, '分镜与主体素材')),
        ])
        setStage(generationMode === 'custom' ? `正在校验第 ${groupIndex + 1}/${submissionGroups.length} 组` : `正在创建第 ${groupIndex + 1}/${submissionGroups.length} 组任务`)
        setProgress(Math.round(52 + ((groupIndex + 1) / submissionGroups.length) * 46))
        const task = await createVideoTask(
          `${group.key.slice(0, 80)} · ${formatTime(new Date().toISOString())}`,
          uploads,
          {
            generationMode,
            customPrompt: generationMode === 'custom' ? customPrompt.trim() : undefined,
            templateId,
            siteProfileId: generationMode === 'automatic' ? siteProfileId : undefined,
            elementIds: subjectMode === 'history' && elementId ? [elementId] : [],
            subjectUploads,
            resultCount,
            durationSeconds: normalizedDurationSeconds,
            actionIntensity,
            cutMode,
          },
          (performance.now() - uploadStartedAt) / 1000,
        )
        if (!firstTask) firstTask = task
        onCreated(task)
      }
      const task = firstTask
      if (!task) throw new Error('没有可提交的素材组')
      setProgress(100)
      setSubmittedNotice(submissionGroups.length > 1
        ? `已批量创建 ${submissionGroups.length} 个独立任务`
        : task.phase === 'ACTION_REQUIRED'
        ? `“${task.title}”已创建，但 ${activeProvider.displayName} 预检需要处理：${task.phaseReasonCode ?? '请查看任务详情'}`
        : `“${task.title}”已进入 ${activeProvider.displayName} 生成队列，可以继续上传下一组素材`)
      const clearSubmittedMaterials = () => {
        setStoryboards([])
        setBatchGroups([])
        setSubjectMode('none')
        setSubjectFiles(createEmptySubjectReferenceFiles())
        setElementId('')
        setResetting(false)
        resetTimerRef.current = null
      }
      if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        clearSubmittedMaterials()
      } else {
        setResetting(true)
        resetTimerRef.current = window.setTimeout(clearSubmittedMaterials, 220)
      }
    } catch (cause) {
      const failure = uploadFailure ?? cause
      setError(failure instanceof Error ? failure.message : '素材提交失败，请检查图片后重试')
    } finally {
      if (uploadAbortRef.current === uploadController) uploadAbortRef.current = null
      setBusy(false)
      setProgress(0)
    }
  }

  return <section className={`composer${busy ? ' is-busy' : ''}${resetting ? ' is-resetting' : ''}`} aria-label="视频制作配置" aria-busy={formLocked}>
    <div className="composer-inputs" inert={formLocked}>
      <div className="upload-panels upload-panels--with-subject">
        <section className={`upload-panel upload-panel--storyboard${storyboards.length ? ' upload-panel--has-items' : ''}`} onDragOver={(event) => {
          if (formLocked) return
          event.preventDefault()
          event.dataTransfer.dropEffect = event.dataTransfer.types.includes(MATERIAL_DRAG_TYPE) ? 'move' : 'copy'
        }} onDrop={(event) => { if (!formLocked) handleDrop(event, storyboards.length) }}>
          <input ref={storyboardInputRef} hidden type="file" multiple disabled={formLocked} accept={IMAGE_FILE_ACCEPT} onChange={(event) => { addFiles(Array.from(event.target.files ?? [])); event.currentTarget.value = '' }} />
          <input ref={batchInputRef} hidden type="file" multiple disabled={formLocked} accept={IMAGE_FILE_ACCEPT} onChange={(event) => { addBatchFiles(Array.from(event.target.files ?? [])); event.currentTarget.value = '' }} />
          <div className="upload-panel-head"><div><h2>有序分镜</h2><small>至少 1 张，最多 {storyboardLimit} 张；拖拽图片调整顺序</small></div><span>{storyboards.length}/{storyboardLimit}</span></div>
          <button type="button" className="upload-zone upload-zone--compact" disabled={formLocked} onClick={() => storyboardInputRef.current?.click()}><span className="upload-icon"><UploadCloud size={22} /></span><span><strong>{storyboards.length ? '继续添加分镜图' : '拖拽或点击上传分镜图'}</strong><small>JPG、PNG、WEBP</small></span></button>
          <button type="button" className="text-button upload-batch-button" disabled={formLocked} onClick={() => batchInputRef.current?.click()}><Images size={16} />按命名批量导入产品图与分镜</button>
          {batchGroups.length ? <div className="batch-groups" aria-live="polite"><strong>批量识别</strong>{batchGroups.map((group) => <div key={group.key}><span>{group.key}</span><small>{group.productFront ? '正面已识别' : '缺正面'} · {group.productBack ? '背面已识别' : '无背面'} · {group.storyboards.length} 张分镜{group.errors.length ? ` · ${group.errors.join('、')}` : ''}</small></div>)}</div> : null}
          {storyboards.length ? <div className="materials-grid" aria-label="分镜图排序列表">{storyboards.map((material, index) => <MaterialCard key={material.id} material={material} bucket="storyboard" index={index} onRemove={() => remove(material.id)} onDropAt={(event, target) => handleDrop(event, target)} onPreview={() => setPreview({ file: material.file, label: `分镜图 ${index + 1}` })} />)}</div> : null}
        </section>
        <SubjectInputPanel
          mode={subjectMode}
          onModeChange={setSubjectMode}
          uploadedFiles={subjectFiles}
          onUploadedFilesChange={setSubjectFiles}
          elements={elements}
          selectedElementId={elementId}
          onSelectedElementIdChange={setElementId}
          storyboardReferenceCount={storyboards.length}
          referenceLimit={referenceLimit || 7}
          disabled={formLocked}
          elementsLoading={elementsLoading}
          elementsError={elementCatalogError}
        />
        <section className="generation-workflow" aria-labelledby="generation-workflow-title">
          <div className="generation-workflow-heading"><div><span>生成方式</span><h2 id="generation-workflow-title">选择提示词路线</h2></div><small>{generationMode === 'custom' ? `自定义提示词直达 ${activeProvider.displayName}` : '根据站点风格自动编排'}</small></div>
          <div className="generation-routes" role="radiogroup" aria-label="生成方式">
            <article className={`generation-route generation-route--custom${generationMode === 'custom' ? ' is-active' : ' is-inactive'}`}>
              <button type="button" className="generation-route-selector" role="radio" aria-checked={generationMode === 'custom'} disabled={formLocked} onClick={() => setGenerationMode('custom')}>
                <span className="generation-route-radio">{generationMode === 'custom' ? <Check size={14} /> : null}</span><span><strong>自定义提示词</strong><small>跳过动作库与站点风格</small></span>
              </button>
              <div className="generation-route-body">
                <CustomPromptField scope="video" label={`${activeModel} 提示词`} value={customPrompt} disabled={formLocked || generationMode !== 'custom'} onChange={setCustomPrompt} placeholder="输入画面动作、镜头和节奏要求" />
              </div>
            </article>

            <article className={`generation-route generation-route--automatic${generationMode === 'automatic' ? ' is-active' : ' is-inactive'}`}>
              <button type="button" className="generation-route-selector" role="radio" aria-checked={generationMode === 'automatic'} disabled={formLocked} onClick={() => setGenerationMode('automatic')}>
                <span className="generation-route-radio">{generationMode === 'automatic' ? <Check size={14} /> : null}</span><span><strong>自动化生成</strong><small>从风格与动作库生成方案</small></span>
              </button>
              <div className="generation-route-body">
                <label className="catalog-field"><span>站点风格</span><select value={siteProfileId} disabled={formLocked || catalogLoading || generationMode !== 'automatic'} onChange={(event) => setSiteProfileId(event.target.value)}>{profiles.map((item) => <option key={item.id} value={item.id}>{item.name}{item.status === 'active' ? '' : ' · 待验收'}</option>)}</select><small>{selectedProfile?.tone ?? '正在加载站点风格'}</small></label>
                <details className="advanced-settings">
                  <summary><Settings size={16} /><span>高级设置</span><ChevronRight size={15} /></summary>
                  <div>
                    <label className="catalog-field"><span>动作强度</span><select disabled={generationMode !== 'automatic'} value={actionIntensity} onChange={(event) => setActionIntensity(event.target.value as typeof actionIntensity)}><option value="low">克制</option><option value="standard">标准</option><option value="high">增强</option></select></label>
                    <label className="catalog-field"><span>切镜方式</span><select disabled={generationMode !== 'automatic'} value={cutMode} onChange={(event) => setCutMode(event.target.value as typeof cutMode)}><option value="explicit_cuts">明确切镜</option><option value="continuous_when_possible">尽量连续</option></select></label>
                  </div>
                </details>
              </div>
            </article>
          </div>
        </section>
      </div>
      </div>
    <div className="composer-submit-row" aria-live="polite">
      <fieldset className="result-count-field composer-result-count"><legend>生成结果数</legend><div className="segmented-control">{([1, 2, 3, 4] as const).map((count) => <label key={count} className={resultCount === count ? 'is-selected' : ''}><input type="radio" name="result-count" value={count} checked={resultCount === count} onChange={() => setResultCount(count)} /><span>{count}</span></label>)}</div></fieldset>
      <label className="composer-duration-field" htmlFor="video-duration"><span>视频时长 <small id="video-duration-options">{durationOptionsLabel}</small></span><span><select id="video-duration" aria-label="视频时长" value={normalizedDurationSeconds} disabled={formLocked} aria-describedby="video-duration-options" onChange={(event) => setDurationSeconds(Number(event.target.value))}>{durationOptions.map((duration) => <option key={duration} value={duration}>{duration}</option>)}</select><small>秒</small></span></label>
      {busy ? <span className="composer-submit-status"><LoaderCircle className="spin" size={14} /><span>{stage}</span><strong>{progress}%</strong></span>
        : <span className="composer-submit-summary"><LockKeyhole size={14} /><span><strong>{resultCount} 个独立任务</strong><small>点击“开始生成”即确认付费提交</small></span></span>}
      <button className="primary-button primary-button--large" disabled={formLocked || catalogLoading || !storyboards.length || !providerAvailable || !subjectReady || !providerInputsSupported || !productionReady || !templateAcceptsCount || !customPromptReady} onClick={() => void submit()}>{busy ? <><LoaderCircle className="spin" size={18} />正在提交</> : resetting ? <><CheckCircle2 size={18} />已提交</> : <><WandSparkles size={18} />开始生成<ArrowRight size={17} /></>}</button>
      {busy ? <div className="composer-submit-progress progress-track"><span style={{ width: `${progress}%` }} /></div> : null}
    </div>
    <div className="composer-feedback" aria-live="polite">
      {error ? <div className="inline-alert inline-alert--danger" role="alert"><AlertTriangle size={17} /><span>{error}</span></div>
        : catalogError ? <div className="inline-alert inline-alert--danger" role="alert"><AlertTriangle size={16} /><span>{catalogError}</span></div>
          : !providerAvailable ? <div className="inline-alert inline-alert--danger" role="alert"><AlertTriangle size={16} />{activeProvider.displayLabel} 当前不可用。请让管理员配置凭据、启用通道并验证连接。</div>
          : !productionReady && !catalogLoading ? <div className="inline-alert" role="alert"><CircleAlert size={17} /><span>{generationMode === 'automatic' ? '当前站点风格尚未通过生产验收。' : '默认生产规格当前不可用。'}</span></div>
          : !subjectReady ? <div className="inline-alert" role="alert"><CircleAlert size={17} /><span>{subjectMode === 'upload' ? subjectValidation.errors[0] : '请选择一个可用的历史主体，或清除主体后按默认方式生成。'}</span></div>
          : !providerInputsSupported ? <div className="inline-alert inline-alert--danger" role="alert"><AlertTriangle size={16} />当前模型 {activeModel} 最多接收 {referenceLimit} 张图片；系统不会静默丢弃分镜。</div>
            : submittedNotice ? <div className="inline-alert inline-alert--success" role="status"><CheckCircle2 size={17} /><span>{submittedNotice}</span></div>
              : notice ? <div className="inline-alert" role="status"><CircleAlert size={17} /><span>{notice}</span></div>
                : !storyboards.length ? <div className="inline-alert"><CircleAlert size={17} /><span>请至少上传 1 张分镜图</span></div>
                  : !templateAcceptsCount ? <div className="inline-alert" role="alert"><CircleAlert size={17} /><span>当前模板接受 {selectedTemplate?.minImages}–{selectedTemplate?.maxImages} 张分镜图</span></div>
                    : !customPromptReady ? <div className="inline-alert" role="alert"><CircleAlert size={17} /><span>请输入自定义提示词，或切换到自动化生成。</span></div>
                  : null}
    </div>
    {preview ? <ImagePreview file={preview.file} label={preview.label} onClose={() => setPreview(null)} /> : null}
  </section>
}

function ImageVideoComposerSheet({ seed, system, actorId, onClose, onCreated }: {
  seed: RemixSeed
  system: SystemStatus | null
  actorId: string | null
  onClose: () => void
  onCreated: (task: Task) => void
}) {
  useEffect(() => {
    document.body.classList.add('modal-open')
    return () => document.body.classList.remove('modal-open')
  }, [])

  return createPortal(<div className="image-composer-sheet-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
    <section className="image-composer-sheet" role="dialog" aria-modal="true" aria-labelledby="image-composer-sheet-title">
      <header><div><span>图片中心</span><h2 id="image-composer-sheet-title">视频制作</h2></div><button type="button" className="icon-button" onClick={onClose} aria-label="关闭视频制作" title="关闭"><X size={18} /></button></header>
      <div className="image-composer-sheet__body"><ProductionComposer key={seed.id} seed={seed} system={system} actorId={actorId} onCreated={onCreated} /></div>
    </section>
  </div>, document.body)
}

function SectionHeading({ title, count, action }: { title: string; count?: number; action?: React.ReactNode }) {
  return <div className="section-heading"><div><h2>{title}</h2>{typeof count === 'number' ? <span className="count-badge">{count}</span> : null}</div>{action}</div>
}

function ProcessingRow({ task, onOpen }: { task: Task; onOpen: () => void }) {
  const variants = task.variants.filter((item) => ['RUNNING', 'PENDING', 'UNKNOWN'].includes(item.generationStatus))
  const progress = providerProgress(task.phase, task.generationProvider)
  return <button type="button" className="processing-row" onClick={onOpen} aria-label={`查看任务：${task.title}`}>
    <TaskThumb task={task} />
    <span className="processing-main"><span className="processing-main-head"><strong>{task.title}</strong><ProviderBadge provider={task.generationProvider} /><TaskStatusBadge task={task} /></span><span>{progress.label ?? (task.phase === 'GENERATING' ? `正在生成 ${variants.map(variantDisplayName).join('、') || '视频'}` : taskStatus(task).label)}</span></span>
    <span className="progress-cell"><span className="progress-summary"><span>{progress.displayLabel} 进度</span><strong>{progress.percent}%</strong></span><span className={`progress-track ${progress.cssClass}`} aria-label={`${progress.displayLabel} 任务进度 ${progress.percent}%`}><span style={{ width: `${progress.percent}%` }} /></span></span>
    <span className="elapsed"><Clock3 size={14} /><TaskElapsed task={task} /></span>
    <span className="processing-row-action">查看<ChevronRight size={16} /></span>
  </button>
}

function AttentionItem({ task, onOpen, onDismiss }: { task: Task; onOpen: () => void; onDismiss: () => void }) {
  const unknownVariant = task.variants.find((variant) => variant.generationStatus === 'UNKNOWN')
  const unknown = Boolean(unknownVariant)
  const isWaiting = task.phase === 'AWAITING_CONFIRMATION'
  const reason = task.phase === 'AWAITING_CONFIRMATION'
    ? '等待确认视频动作方案'
    : unknown
      ? variantExecutionMessage(unknownVariant!, task.generationProvider)
      : isAnalysisFailure(task)
        ? taskFailureMessage(task)
        : taskFailureMessage(task)
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
  const [downloadBusy, setDownloadBusy] = useState(false)
  const [downloadError, setDownloadError] = useState('')
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
  const download = async () => {
    if (!variant.downloadArtifactId) return
    setDownloadBusy(true)
    setDownloadError('')
    try {
      await saveArtifact(variant.downloadArtifactId, `${task.title}-${variantFileToken(variant)}.mp4`)
    } catch (cause) {
      setDownloadError(cause instanceof Error ? cause.message : '视频下载失败，请稍后重试')
    } finally {
      setDownloadBusy(false)
    }
  }
  return <article className={`result-card${feedbackPanel ? ' has-feedback-panel' : ''}`}>
    <button className="result-cover" onClick={ready ? onPlay : onOpen} aria-label={ready ? `播放 ${task.title}` : `查看 ${task.title}`}>
      {product ? <AuthenticatedImage src={product.thumbnailUrl} alt={`${task.title} 视频封面`} /> : <Film size={30} />}
      <span className={`variant-label ${variantLabelClass(variant)}`}>{variantShortLabel(variant)}</span>
      {ready ? <span className="play-button"><Play size={21} fill="currentColor" /></span> : <span className="result-state"><StatusBadge value={variant.generationStatus} /></span>}
      <span className="duration">10s</span>
    </button>
    <div className="result-body"><div><strong>{task.title}</strong><span>{variantDisplayName(variant)} · {formatTime(task.updatedAt)}</span></div>
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
      {ready ? <><button className="icon-button" onClick={onPlay} aria-label="播放视频" title="播放"><Play size={17} /></button><button className="icon-button" disabled={downloadBusy} onClick={() => void download()} aria-label="下载视频" title="下载">{downloadBusy ? <LoaderCircle className="spin" size={17} /> : <Download size={17} />}</button><button className="icon-button" onClick={onOpen} aria-label="查看任务详情" title="查看任务详情"><Eye size={17} /></button></> : <button className="compact-button" onClick={onOpen}>查看状态</button>}
      <button className="remix-button" onClick={onRemix}><RotateCcw size={15} />同素材再制作</button>
    </div>{downloadError ? <small className="result-action-error" role="alert">{downloadError}</small> : null}</div>
  </article>
}

type PlanShot = {
  entryState?: string
  action?: string
  exitState?: string
  camera?: string
  productDisplay?: string
  shotFunction?: string
  durationWeight?: number
}
type VariantPlan = { continuityStrategy?: string; shots?: PlanShot[] }
type AnalysisResult = {
  garmentFacts?: { category?: string; mainColor?: string; secondaryColor?: string; print?: string; logo?: string; text?: string; fit?: string; frontSellingPoints?: string[]; backSellingPoints?: string[] }
  storyboardFacts?: Array<{ scene?: string; framing?: string; pose?: string; actionCandidates?: string[] }>
  consistencyObservations?: { summary?: string }
  riskFlags?: string[]
  stablePlan?: VariantPlan
  dynamicPlan?: VariantPlan
}

async function copyText(value: string) {
  if (window.isSecureContext && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value)
      return
    } catch {
      // Fall through for browsers that expose the API but deny clipboard access.
    }
  }

  const textarea = document.createElement('textarea')
  textarea.value = value
  textarea.style.position = 'fixed'
  textarea.style.left = '-9999px'
  textarea.style.top = '0'
  document.body.appendChild(textarea)
  textarea.focus()
  textarea.select()
  textarea.setSelectionRange(0, value.length)
  try {
    if (!document.execCommand('copy')) throw new Error('Clipboard copy was rejected')
  } finally {
    textarea.remove()
  }
}

function PromptBlock({ variant, value, disabled, dirty, onChange }: { variant: Variant; value: string; disabled: boolean; dirty: boolean; onChange: (value: string) => void }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    await copyText(value)
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
    <header><span className={`variant-label ${stable ? 'variant-label--a' : 'variant-label--b'}`}>{variantKindShortLabel(kind)}</span><div><h3>{variantKindDisplayName(kind)}</h3><p>{stable ? '保持人物稳定与服装结构准确，清晰展示印花和版型' : '强化广告开场和动作变化，同时保持服装准确'}</p></div></header>
    <div className="plan-facts"><div><span>{stable ? '视频开场' : '开场钩子'}</span><strong>{first?.shotFunction ?? (stable ? '清晰产品开场' : '强动态广告开场')}</strong></div><div><span>人物动作</span><strong>{first?.action ?? '自然动作'}</strong></div><div><span>镜头运动</span><strong>{first?.camera ?? '稳定运镜'}</strong></div><div><span>展示重点</span><strong>{first?.productDisplay ?? '服装轮廓与细节'}</strong></div></div>
    {shots.length > 1 ? <div className="shot-strip">{shots.map((shot, index) => <span key={`${shot.shotFunction}-${index}`}><strong>动作段 {index + 1}</strong><small>{[shot.entryState, shot.action, shot.exitState].filter(Boolean).join(' → ')}</small></span>)}</div> : null}
    <div className={`risk-line ${risks.length ? 'risk-line--warning' : ''}`}>{risks.length ? <AlertTriangle size={15} /> : <ShieldCheck size={15} />}<span>{risks.length ? `风险提示：${formatRiskFlags(risks)}` : '未发现明显的产品准确性风险'}</span></div>
    {variant ? <><PromptBlock variant={variant} value={prompt} dirty={promptDirty} disabled={disabled} onChange={onPromptChange} /><PromptRevision kind={kind} instruction={revisionInstruction} message={revisionMessage} disabled={disabled} activeMode={activeRevisionMode} onInstructionChange={onRevisionInstructionChange} onSubmit={onPromptRevision} /></> : null}
  </section>
}

function VariantStatus({ task, variant, onChanged, onPlay }: { task: Task; variant: Variant; onChanged: () => Promise<void>; onPlay: () => void }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const ready = Boolean(variant.downloadArtifactId)
  const unknown = variant.generationStatus === 'UNKNOWN'
  const downloading = variant.downloadStatus === 'DOWNLOADING'
  const restore = async () => {
    setBusy(true)
    setError('')
    try {
      await restoreOutput(task.id, variant.kind)
      await onChanged()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '远端成品恢复失败，请稍后重试')
    } finally { setBusy(false) }
  }
  const download = async () => {
    if (!variant.downloadArtifactId) return
    setBusy(true)
    setError('')
    try {
      await saveArtifact(variant.downloadArtifactId, `${task.title}-${variantFileToken(variant)}.mp4`)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '视频下载失败，请稍后重试')
    } finally { setBusy(false) }
  }
  const canRestore = !ready
    && !downloading
    && ['SUCCEEDED', 'PARTIAL'].includes(variant.generationStatus)
    && (variant.downloadStatus === 'FAILED' || task.phase === 'ACTION_REQUIRED')
  return <div className="variant-status"><span className={`variant-label ${variantLabelClass(variant)}`}>{variantShortLabel(variant)}</span><div><strong>{variantDisplayName(variant)}</strong><ProviderBadge provider={variant.provider || task.generationProvider} /><StatusBadge value={variant.generationStatus} /><small>{variantExecutionMessage(variant, task.generationProvider, task.phase)}</small>{error ? <small className="variant-action-error" role="alert">{error}</small> : null}</div><div className="variant-status-actions">
    {ready ? <><button className="compact-button" onClick={onPlay}><Play size={15} />播放</button><button className="compact-button" disabled={busy} onClick={() => void download()}>{busy ? <LoaderCircle className="spin" size={15} /> : <Download size={15} />}下载</button></> : null}
    {downloading ? <button className="compact-button" disabled><LoaderCircle className="spin" size={15} />下载中</button> : null}
    {canRestore ? <button className="compact-button" disabled={busy} onClick={() => void restore()}>{busy ? <LoaderCircle className="spin" size={15} /> : <RefreshCw size={15} />}恢复远端成品</button> : null}
    {unknown ? <button className="compact-button" onClick={() => void onChanged()}><RefreshCw size={15} />重新查询状态</button> : null}
  </div></div>
}

function HistoricalPrompt({
  task,
  variant,
  selected,
}: {
  task: Task
  variant: Variant
  selected: boolean
}) {
  const [copyStatus, setCopyStatus] = useState<'idle' | 'copied' | 'failed'>('idle')
  const copy = async () => {
    try {
      await copyText(variant.promptText)
      setCopyStatus('copied')
    } catch {
      setCopyStatus('failed')
    }
    window.setTimeout(() => setCopyStatus('idle'), 1600)
  }
  return <article className={`history-prompt${selected ? ' is-selected' : ''}`}>
    <header>
      <span className={`variant-label ${variantLabelClass(variant)}`}>{variantShortLabel(variant)}</span>
      <span><strong>{variantDisplayName(variant)}</strong><small>{task.workflowKind === 'FIXED_TEMPLATE' ? task.settings?.generationMode === 'custom' ? '自定义直达快照' : '自动化编译快照' : selected ? '将复用此提示词' : '本次不复用'}</small></span>
      <button className="compact-button" type="button" onClick={() => void copy()} aria-live="polite">{copyStatus === 'copied' ? <Check size={15} /> : <Copy size={15} />}{copyStatus === 'copied' ? '已复制' : copyStatus === 'failed' ? '复制失败' : '复制'}</button>
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
  const provider = providerPresentation(task.generationProvider)
  const isFixedWorkflow = task.workflowKind === 'FIXED_TEMPLATE'
  const isCustomWorkflow = isFixedWorkflow && task.settings?.generationMode === 'custom'
  const stable = task.variants.find((variant) => variant.kind === 'STABLE')
  const dynamic = task.variants.find((variant) => variant.kind === 'DYNAMIC')
  const savePrompts = async (sourceTask = task) => {
    if (!promptDrafts.stable.trim() || !promptDrafts.dynamic.trim()) throw new Error('稳定展示和动态广告的提示词不能为空')
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
      : `重新生成${kind === 'STABLE' ? '稳定展示' : '动态广告'}方案，在不改变服装事实和方案定位的前提下优化动作和镜头。`
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
  const cancel = async () => {
    if (!window.confirm(`确定取消此任务吗？已提交到 ${providerPresentation(task.generationProvider).displayName} 的远端任务可能无法撤回。`)) return
    setBusy(true)
    setError('')
    try {
      await cancelTask(task.id)
      await onChanged()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '任务取消失败，请稍后重试')
    } finally { setBusy(false) }
  }
  const isConfirmation = !isFixedWorkflow && task.phase === 'AWAITING_CONFIRMATION'
  const isGenerating = ACTIVE_PHASES.has(task.phase) && task.phase !== 'DRAFT' && task.phase !== 'ANALYZING'
  const isCompleted = RESULT_PHASES.has(task.phase)
  const canReuse = !isFixedWorkflow && isCompleted && task.actionCapabilities.canRegenerate && reusableVariants.length > 0
  const analysisFailure = isAnalysisFailure(task)
  const productionStageKeys = visibleProductionStageKeys(
    task.workflowKind,
    task.settings?.generationMode,
  )
  const currentStep = currentProductionStageIndex(
    task.phase,
    task.workflowKind,
    task.settings?.generationMode,
  )
  const needsRecovery = task.phase === 'ACTION_REQUIRED'
  const confirmationChoice = confirmationKinds.length === 2
    ? 'BOTH'
    : confirmationKinds[0] ?? task.variants[0]?.kind
  const confirmationLabel = confirmationKinds.length === 2
    ? '全部方案'
    : variantKindDisplayName(confirmationKinds[0] ?? task.variants[0]?.kind ?? 'STABLE')
  return <div className="workspace-view">
    <section className="production-workspace" aria-labelledby="detail-title">
      <header className="drawer-header">
        <button className="icon-button" onClick={onClose} aria-label="关闭任务详情"><ArrowLeft size={19} /></button>
        <div className="drawer-header-main"><span>任务 / {isConfirmation ? '方案确认' : RESULT_PHASES.has(task.phase) ? '视频结果' : analysisFailure ? '分析恢复' : needsRecovery ? '异常处理' : '生产进度'}</span><h1 id="detail-title">{task.title}</h1></div>
        <div className="drawer-header-actions"><ProviderBadge provider={task.generationProvider} /><TaskStatusBadge task={task} /></div>
      </header>
      <div className="workspace-stages" aria-label="制作阶段">{productionStageKeys.map((stageKey, index) => {
        const label = stageKey === 'MATERIALS' ? '素材'
          : stageKey === 'TEMPLATE' ? '模板'
            : stageKey === 'PREFLIGHT' ? '预检'
              : stageKey === 'ANALYSIS' ? '分析'
                : stageKey === 'PLAN' ? '方案'
                  : stageKey === 'RESULT' ? '结果'
                    : provider.kind === 'legacy' ? '历史任务生成' : `${provider.displayName}生成`
        return <div key={stageKey} aria-current={index === currentStep ? 'step' : undefined} className={index < currentStep ? 'is-complete' : index === currentStep ? 'is-current' : ''}><span>{index < currentStep ? <Check size={14} /> : index + 1}</span><strong>{label}</strong></div>
      })}</div>
      <div className="drawer-content">
        <section className="source-summary"><div className="source-assets">{[...task.assets].sort((a, b) => a.order - b.order).map((asset, index) => <figure key={asset.id}><AuthenticatedImage src={asset.thumbnailUrl} alt={asset.originalFilename} /><figcaption>{asset.role === 'PRODUCT' || asset.usedForGeneration === false ? '产品图' : `分镜 ${index + 1}`}</figcaption></figure>)}</div><div className="garment-summary"><span>{isCustomWorkflow ? '自定义直达快照' : isFixedWorkflow ? '自动化生成快照' : '服装识别摘要'}</span><strong>{isCustomWorkflow ? '自定义提示词 · 默认生产规格' : isFixedWorkflow ? `${task.siteProfileId ?? '未知站点'} · 自动编排` : [analysis?.garmentFacts?.category, analysis?.garmentFacts?.mainColor, analysis?.garmentFacts?.fit].filter(Boolean).join(' · ') || '正在整理服装信息'}</strong><p>{isCustomWorkflow ? `提示词原文直达 · ${task.variants.length} 个结果` : isFixedWorkflow ? `动作 ${String(task.settings?.actionIntensity ?? 'standard')} · ${task.variants.length} 个结果` : analysis?.consistencyObservations?.summary ?? '系统将优先保持服装结构、颜色、印花和文字准确。'}</p></div></section>
        {analysisFailure ? <section className="analysis-recovery" role="alert">
          <span className="analysis-recovery-icon"><AlertTriangle size={22} /></span>
          <div><span>方案尚未生成</span><h2>{taskStatus(task).label}</h2><p>{taskFailureMessage(task)} 重新分析会继续使用当前素材，并按素材数量重新计算等待时间。</p></div>
          <button className="primary-button" disabled={busy || !task.actionCapabilities.canRetryAnalysis} onClick={() => void retryAnalysis()}>{busy ? <LoaderCircle className="spin" size={17} /> : <RefreshCw size={17} />}重新分析方案</button>
        </section> : null}
        {needsRecovery && !analysisFailure ? <section className="analysis-recovery" role="alert">
          <span className="analysis-recovery-icon"><AlertTriangle size={22} /></span>
          <div><span>提交前预检已停止</span><h2>{provider.displayLabel} 未收到生成任务</h2><p>{taskFailureMessage(task)}</p></div>
        </section> : null}
        {isConfirmation ? <>
          <div className="drawer-section-title"><div><span>步骤 2 / 3</span><h2>确认视频方案</h2></div><p>确认后将保存提示词原文快照，并原样提交给 {provider.displayLabel}。</p></div>
          <div className={`plans-grid${task.variants.length === 1 ? ' plans-grid--single' : ''}`}>
            {stable ? <PlanPanel kind="STABLE" plan={analysis?.stablePlan} variant={stable} risks={analysis?.riskFlags ?? []} prompt={promptDrafts.stable} promptDirty={promptDirty.STABLE} disabled={busy} revisionInstruction={revisionInstructions.STABLE} revisionMessage={revisionMessages.STABLE} activeRevisionMode={activeRevision?.kind === 'STABLE' ? activeRevision.mode : null} onPromptChange={(value) => { setPromptDrafts((current) => ({ ...current, stable: value })); setPromptDirty((current) => ({ ...current, STABLE: true })) }} onRevisionInstructionChange={(value) => setRevisionInstructions((current) => ({ ...current, STABLE: value }))} onPromptRevision={(mode) => void revisePrompt('STABLE', mode)} /> : null}
            {dynamic ? <PlanPanel kind="DYNAMIC" plan={analysis?.dynamicPlan} variant={dynamic} risks={analysis?.riskFlags ?? []} prompt={promptDrafts.dynamic} promptDirty={promptDirty.DYNAMIC} disabled={busy} revisionInstruction={revisionInstructions.DYNAMIC} revisionMessage={revisionMessages.DYNAMIC} activeRevisionMode={activeRevision?.kind === 'DYNAMIC' ? activeRevision.mode : null} onPromptChange={(value) => { setPromptDrafts((current) => ({ ...current, dynamic: value })); setPromptDirty((current) => ({ ...current, DYNAMIC: true })) }} onRevisionInstructionChange={(value) => setRevisionInstructions((current) => ({ ...current, DYNAMIC: value }))} onPromptRevision={(mode) => void revisePrompt('DYNAMIC', mode)} /> : null}
          </div>
        </> : null}
        {isGenerating || RESULT_PHASES.has(task.phase) || (task.phase === 'ACTION_REQUIRED' && !analysisFailure) ? <>
          <div className="drawer-section-title"><div><span>步骤 3 / 3 · {provider.displayLabel}</span><h2>{RESULT_PHASES.has(task.phase) ? '视频结果' : needsRecovery ? `${provider.displayLabel} 任务需要处理` : `${provider.displayLabel} 生成进度`}</h2></div></div>
          <TaskTimingTimeline task={task} />
          <div className="variant-status-list">{task.variants.map((variant) => <VariantStatus key={variant.id} task={task} variant={variant} onChanged={onChanged} onPlay={() => onPlay(variant)} />)}</div>
        </> : null}
        {isCompleted && reusableVariants.length ? <>
          <div className="drawer-section-title history-prompt-title"><div><span>历史方案</span><h2>本次使用的提示词</h2></div><p>提示词为任务完成时的只读快照</p></div>
          <div className={`history-prompts${reusableVariants.length === 1 ? ' history-prompts--single' : ''}`}>
            {reusableVariants.map((variant) => <HistoricalPrompt key={variant.id} task={task} variant={variant} selected={reuseKinds.includes(variant.kind)} />)}
          </div>
        </> : null}
        {task.phase === 'ANALYZING' ? <AnalysisProgress task={task} /> : null}
        {error ? <div className="inline-alert inline-alert--danger" role="alert"><AlertTriangle size={17} />{error}</div> : null}
        <details className="technical-details"><summary><span><MoreHorizontal size={17} />技术信息</span><ChevronRight size={16} /></summary><div><dl><dt>Task ID</dt><dd>{task.id}</dd><dt>Session ID</dt><dd>{task.clientTaskId}</dd><dt>工作流</dt><dd>{isFixedWorkflow ? '固定模板' : '历史分析流程'}</dd><dt>生成通道</dt><dd>{provider.displayLabel}</dd>{provider.kind === 'legacy' ? <><dt>历史项目 ID</dt><dd>{task.canvasProjectUuid ?? '尚未分配'}</dd></> : <><dt>调用方式</dt><dd>{provider.displayLabel} / 远端任务查询</dd></>}<dt>原始状态</dt><dd>{task.phase}</dd><dt>状态版本</dt><dd>{task.stateVersion}</dd><dt>错误代码</dt><dd>{task.phaseReasonCode ?? '无'}</dd></dl><div className="prompt-hashes">{task.variants.map((variant) => <span key={variant.id}><strong>{variantDisplayName(variant)} · {providerPresentation(variant.provider || task.generationProvider).displayLabel}</strong><code>{variant.providerTaskId ? `${providerPresentation(variant.provider || task.generationProvider).kind === 'kling' ? 'remoteTaskId' : 'taskId'}: ${variant.providerTaskId}` : `Prompt Hash: ${variant.promptHash ?? '尚未锁定'}`}</code><small>{variant.executionBackend ?? '尚未进入生成通道'}</small>{variant.errorCode ? <small>错误：{variant.errorCode}{variantErrorMessage(variant) ? ` · ${variantErrorMessage(variant)}` : ''}{variantErrorRetryable(variant) === true ? ' · 可以重试' : variantErrorRetryable(variant) === false ? ' · 需要人工处理' : ''}</small> : null}{variantErrorDetails(variant) ? <code>{JSON.stringify(variantErrorDetails(variant))}</code> : null}</span>)}</div></div></details>
      </div>
      {task.actionCapabilities.canRegenerate || task.actionCapabilities.canCancel || isConfirmation ? <footer className={`drawer-footer${canReuse ? ' drawer-footer--reuse' : ''}${isConfirmation ? ' drawer-footer--confirmation' : ''}`}>
        <div className="drawer-footer-actions">
          {task.actionCapabilities.canCancel ? <button className="secondary-button secondary-button--danger" disabled={busy} onClick={() => void cancel()}><X size={16} />取消任务</button> : null}
          {task.actionCapabilities.canRegenerate && !canReuse ? <button className="secondary-button" onClick={onRemix}><RotateCcw size={16} />使用相同素材再制作</button> : null}
        </div>
        {canReuse ? <div className="reuse-controls">
          <fieldset>
            <legend>选择复用方案</legend>
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
                <span className={`variant-label ${kind === 'STABLE' ? 'variant-label--a' : 'variant-label--b'}`}>{variantKindShortLabel(kind)}</span>
                <span><strong>{variantKindDisplayName(kind)}</strong>{!available ? <small>无历史提示词</small> : null}</span>
              </label>
            })}
          </fieldset>
          <div>
            {!reuseKinds.length ? <small role="alert">请至少勾选一个方案</small> : <small>将复用全部素材及所选提示词，并跳过图片分析</small>}
            <button className="primary-button primary-button--large" disabled={!reuseKinds.length} onClick={() => onReuse(reuseKinds)}><RotateCcw size={17} />一键复用并生成 {reuseKinds.length || ''} 个结果</button>
          </div>
        </div> : null}
        {isConfirmation ? <div className="confirmation-submit">
          {task.variants.length > 1 ? <fieldset className="confirmation-variant-picker">
            <legend>本次生成</legend>
            <div>
              <label className={confirmationChoice === 'STABLE' ? 'is-selected' : ''}>
                <input type="radio" name={`confirmation-variant-${task.id}`} checked={confirmationChoice === 'STABLE'} disabled={busy} onChange={() => setConfirmationKinds(['STABLE'])} />
                <span>稳定展示</span>
              </label>
              <label className={confirmationChoice === 'BOTH' ? 'is-selected' : ''}>
                <input type="radio" name={`confirmation-variant-${task.id}`} checked={confirmationChoice === 'BOTH'} disabled={busy} onChange={() => setConfirmationKinds(['STABLE', 'DYNAMIC'])} />
                <span>全部方案</span>
              </label>
              <label className={confirmationChoice === 'DYNAMIC' ? 'is-selected' : ''}>
                <input type="radio" name={`confirmation-variant-${task.id}`} checked={confirmationChoice === 'DYNAMIC'} disabled={busy} onChange={() => setConfirmationKinds(['DYNAMIC'])} />
                <span>动态广告</span>
              </label>
            </div>
          </fieldset> : null}
          <button className="primary-button primary-button--large" disabled={busy} onClick={() => void confirm()}>{busy ? <LoaderCircle className="spin" size={18} /> : <Check size={18} />}确认并生成 {confirmationLabel}</button>
        </div> : null}
      </footer> : null}
    </section>
  </div>
}

function HomeView({ active, tasks, seed, system, actorId, onCreated, onOpen, onView, onPlay, onRemix, onFeedbackChanged }: { active: boolean; tasks: Task[]; seed: RemixSeed | null; system: SystemStatus | null; actorId: string | null; onCreated: (task: Task, open?: boolean) => void; onOpen: (task: Task) => void; onView: (view: View) => void; onPlay: (task: Task, variant: Variant) => void; onRemix: (task: Task) => void; onFeedbackChanged: (task: Task) => void }) {
  const activeVideo = system?.videoGeneration ?? system?.kling
  const activeModel = activeVideo?.model || activeVideo?.models[0] || '当前管理端模型'
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
  return <div className="home-view" hidden={!active}>
    <div className="home-title"><div><h1>视频制作</h1><p>上传分镜与主体素材，使用 {activeModel} 生成视频。</p></div><div className="home-title-actions"><span className="quick-stat"><strong>{activeCount}</strong><small>处理中</small></span><span className="quick-stat"><strong>{completedCount}</strong><small>已完成</small></span><button className="text-button" onClick={() => onView('records')}>查看任务<ChevronRight size={15} /></button></div></div>
    <div className="home-hero-grid home-hero-grid--full">
      <ProductionComposer key={seed?.id ?? 'new-production'} seed={seed} onCreated={onCreated} system={system} actorId={actorId} />
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
    { value: 'attention', label: '需要处理', test: (task) => task.phase === 'AWAITING_CONFIRMATION' || task.phase === 'ACTION_REQUIRED' },
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
  const completedResults = completed
    .flatMap((task) => task.variants.map((variant) => ({ task, variant })))
    .filter(({ variant }) => variant.downloadArtifactId)
    .sort((left, right) => Date.parse(right.task.updatedAt) - Date.parse(left.task.updatedAt))
  const displayedCompletedResults = filter === 'all' ? completedResults.slice(0, 3) : completedResults
  const attentionCount = tasks.filter((task) => task.phase === 'AWAITING_CONFIRMATION' || task.phase === 'ACTION_REQUIRED').length
  const activeCount = tasks.filter((task) => ACTIVE_PHASES.has(task.phase)).length
  const doneCount = tasks.filter((task) => COMPLETED_PHASES.has(task.phase)).length
  return <div className="page-view"><div className="page-title"><div><span>Production Tasks</span><h1>任务</h1><p>查找任务、继续处理，或直接播放和下载已完成视频。</p></div><label className="search-field"><Search size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索任务名称" aria-label="搜索任务名称" /></label></div>
    <section className="records-overview" aria-label="任务概览">
      <button type="button" className={filter === 'all' ? 'is-active' : ''} aria-pressed={filter === 'all'} onClick={() => setFilter('all')}><span className="records-overview-dot is-blue" /><span><small>全部任务</small><strong>{tasks.length}</strong></span></button>
      <button type="button" className={filter === 'attention' ? 'is-active' : ''} aria-pressed={filter === 'attention'} onClick={() => setFilter('attention')}><span className="records-overview-dot is-amber" /><span><small>需要处理</small><strong>{attentionCount}</strong></span></button>
      <button type="button" className={filter === 'active' ? 'is-active' : ''} aria-pressed={filter === 'active'} onClick={() => setFilter('active')}><span className="records-overview-dot is-purple" /><span><small>生产中</small><strong>{activeCount}</strong></span></button>
      <button type="button" className={filter === 'done' ? 'is-active' : ''} aria-pressed={filter === 'done'} onClick={() => setFilter('done')}><span className="records-overview-dot is-green" /><span><small>已完成</small><strong>{doneCount}</strong></span></button>
    </section>
    <div className="filter-tabs">{groups.map((item) => { const count = tasks.filter(item.test).length; return <button key={item.value} className={filter === item.value ? 'is-active' : ''} onClick={() => setFilter(item.value)}>{item.label}<span>{count}</span></button> })}</div>
    {displayedCompletedResults.length ? <section className={`records-completed${filter === 'all' ? ' records-completed--preview' : ''}`} aria-label={filter === 'all' ? '最近完成的视频' : '全部已完成视频'}><SectionHeading title={filter === 'all' ? '最近完成' : '视频结果'} count={displayedCompletedResults.length} action={filter === 'all' ? <button type="button" className="text-button" onClick={() => setFilter('done')}>查看全部已完成<ChevronRight size={15} /></button> : undefined} /><div className="results-grid results-grid--library">{displayedCompletedResults.map(({ task, variant }) => <ResultCard key={variant.id} task={task} variant={variant} onPlay={() => onPlay(task, variant)} onRemix={() => onRemix(task)} onOpen={() => onOpen(task)} onFeedbackChanged={onFeedbackChanged} />)}</div></section> : null}
    {listRows.length ? <div className="task-table"><div className="task-table-head"><span>产品 / 任务</span><span>当前状态</span><span>结果进度</span><span>更新时间</span><span /></div>{listRows.map((task) => <button className="task-table-row" key={task.id} onClick={() => onOpen(task)}><span className="task-name-cell"><TaskThumb task={task} /><span><strong>{task.title}</strong><small>{task.assetCount} 张素材</small></span></span><span><TaskStatusBadge task={task} />{task.phaseReasonCode ? <small>{isAnalysisFailure(task) ? taskFailureMessage(task) : task.phaseReasonCode}</small> : null}</span><span className="mini-variants">{task.variants.map((variant) => <i key={variant.id} className={variant.generationStatus === 'FAILED' ? 'is-failed' : variant.generationStatus === 'SUCCEEDED' ? 'is-done' : ''} aria-label={variantDisplayName(variant)} title={variantDisplayName(variant)}>{variantShortLabel(variant)}</i>)}</span><span>{formatTime(task.updatedAt)}</span><span><ChevronRight size={17} /></span></button>)}</div> : null}
    {hasMore ? <div className="records-load-more"><button className="secondary-button" disabled={loadingMore} onClick={onLoadMore}>{loadingMore ? <LoaderCircle className="spin" size={16} /> : null}{loadingMore ? '正在加载' : '加载更早记录'}</button></div> : null}
    {!visible.length ? <EmptyState icon={<ListVideo size={24} />} title={`没有${group.label === '全部' ? '' : group.label}记录`} description="任务状态变化后会自动归入对应分类。" /> : null}
  </div>
}

type ContentLibraryScope = 'general' | 'brand' | 'subjects'
type ContentLibraryKind = 'actions' | 'styles'
type ActionCategoryFilter = MotionActionSummary['category'] | 'all'

const ACTION_CATEGORY_LABELS: Record<MotionActionSummary['category'], string> = {
  outfit: '整体穿搭',
  detail: '图案与面料',
  back: '背面展示',
  interaction: '人镜交流',
  product: '商品交互',
}

function styleStatus(profile: SiteStyleProfileSummary) {
  if (profile.status === 'draft') return { label: '研究草稿', warning: true }
  if (profile.status === 'retired') return { label: '已停用', warning: true }
  return {
    label: profile.libraryScope === 'brand' ? '站点已验证' : '规则已验证',
    warning: profile.evidenceLevel !== 'verified_site',
  }
}

function ContentLibraryView({ actorId, canDeleteSubjects, canEditCatalog }: {
  actorId: string | null
  canDeleteSubjects: boolean
  canEditCatalog: boolean
}) {
  const [scope, setScope] = useState<ContentLibraryScope>('general')
  const [kind, setKind] = useState<ContentLibraryKind>('actions')
  const tab = scope === 'subjects' ? 'subjects' : kind
  const [query, setQuery] = useState('')
  const deferredQuery = useDeferredValue(query.trim().toLowerCase())
  const [category, setCategory] = useState<ActionCategoryFilter>('all')
  const [brandFilter, setBrandFilter] = useState('all')
  const [actions, setActions] = useState<MotionActionSummary[]>([])
  const [profiles, setProfiles] = useState<SiteStyleProfileSummary[]>([])
  const [templates, setTemplates] = useState<VideoTemplateSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [copiedActionId, setCopiedActionId] = useState('')
  const [editor, setEditor] = useState<
    | { kind: 'action'; item?: MotionActionSummary; initialScope?: 'general' | 'brand' }
    | { kind: 'style'; item?: SiteStyleProfileSummary; initialScope?: 'general' | 'brand' }
    | null
  >(null)

  useEffect(() => {
    let active = true
    Promise.all([getMotionActions(), getSiteStyleProfiles(), getVideoTemplates()])
      .then(([nextActions, nextProfiles, nextTemplates]) => {
        if (!active) return
        setActions(nextActions)
        setProfiles(nextProfiles)
        setTemplates(nextTemplates)
        setError('')
      })
      .catch((cause) => {
        if (active) setError(cause instanceof Error ? cause.message : '内容库加载失败')
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  const templateNames = useMemo(
    () => new Map(templates.map((template) => [template.id, template.name])),
    [templates],
  )
  const actionNames = useMemo(
    () => new Map(actions.map((action) => [action.id, action.label])),
    [actions],
  )
  const visibleActions = useMemo(() => actions.filter((action) => {
    if (action.libraryScope !== scope) return false
    if (scope === 'brand' && brandFilter !== 'all' && action.brandId !== brandFilter) return false
    if (category !== 'all' && action.category !== category) return false
    if (!deferredQuery) return true
    return [
      action.label,
      action.id,
      action.instruction,
      action.purpose,
      ACTION_CATEGORY_LABELS[action.category],
      ...action.requirements,
      ...action.avoid,
    ].join(' ').toLowerCase().includes(deferredQuery)
  }), [actions, brandFilter, category, deferredQuery, scope])
  const visibleProfiles = useMemo(() => profiles.filter((profile) => {
    if (profile.libraryScope !== scope) return false
    if (scope === 'brand' && brandFilter !== 'all' && profile.brandId !== brandFilter) return false
    if (!deferredQuery) return true
    return [
      profile.name,
      profile.tone,
      profile.expressionLanguage,
      profile.audience,
      profile.cameraLanguage,
      profile.openingRule,
      profile.middleRule,
      profile.endingRule,
      ...profile.preferredShots,
      ...profile.productPriorities,
      ...profile.preferredActions.map((id) => actionNames.get(id) ?? id),
    ].join(' ').toLowerCase().includes(deferredQuery)
  }), [actionNames, brandFilter, deferredQuery, profiles, scope])
  const generalActionCount = actions.filter((action) => action.libraryScope === 'general').length
  const generalStyleCount = profiles.filter((profile) => profile.libraryScope === 'general').length
  const brandActionCount = actions.filter((action) => action.libraryScope === 'brand').length
  const brandStyleCount = profiles.filter((profile) => profile.libraryScope === 'brand').length
  const brandNames = useMemo(
    () => new Map(profiles.filter((profile) => profile.libraryScope === 'brand').map((profile) => [profile.id, profile.name])),
    [profiles],
  )
  const hasActiveLibraryFilters = Boolean(deferredQuery)
    || (scope === 'brand' && brandFilter !== 'all')
    || (tab === 'actions' && category !== 'all')

  const copyAction = async (action: MotionActionSummary) => {
    await navigator.clipboard.writeText(action.instruction)
    setCopiedActionId(action.id)
    window.setTimeout(() => setCopiedActionId(''), 1800)
  }

  const catalogSaved = (
    item: MotionActionSummary | SiteStyleProfileSummary,
    kind: 'action' | 'style',
  ) => {
    if (kind === 'action') {
      const saved = item as MotionActionSummary
      setActions((current) => current.some((action) => action.id === saved.id)
        ? current.map((action) => action.id === saved.id ? saved : action)
        : [...current, saved])
    } else {
      const saved = item as SiteStyleProfileSummary
      if (saved.status === 'retired') {
        setProfiles((current) => current.filter((profile) => profile.id !== saved.id))
        setEditor(null)
        return
      }
      setProfiles((current) => current.some((profile) => profile.id === saved.id)
        ? current.map((profile) => profile.id === saved.id ? saved : profile)
        : [...current, saved])
    }
    setEditor(null)
  }

  return <div className="page-view content-library-view">
    <div className="page-title content-library-title">
      <div><span>Production Asset Library</span><h1>内容与主体库</h1><p>通用资产可跨品牌复用，品牌专属资产只服务对应品牌。</p></div>
      {tab !== 'subjects' ? <label className="search-field"><Search size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={tab === 'actions' ? '搜索动作、用途或风险' : '搜索风格、语气或镜头'} aria-label={tab === 'actions' ? '搜索动作库' : '搜索风格库'} /></label> : null}
    </div>

    <section className="library-overview" aria-label="内容库概览">
      <div><span className="library-overview-icon library-overview-icon--blue"><Activity size={20} /></span><span><small>通用动作</small><strong>{generalActionCount}</strong><em>跨品牌复用</em></span></div>
      <div><span className="library-overview-icon library-overview-icon--green"><Clapperboard size={20} /></span><span><small>通用风格</small><strong>{generalStyleCount}</strong><em>不绑定品牌</em></span></div>
      <div><span className="library-overview-icon library-overview-icon--violet"><LockKeyhole size={20} /></span><span><small>品牌风格</small><strong>{brandStyleCount}</strong><em>独立版本与证据</em></span></div>
      <div><span className="library-overview-icon library-overview-icon--orange"><WandSparkles size={20} /></span><span><small>品牌动作</small><strong>{brandActionCount}</strong><em>仅限所属品牌</em></span></div>
    </section>

    <div className="library-scope-tabs" role="tablist" aria-label="内容库归属">
      <button type="button" role="tab" aria-selected={scope === 'general'} className={scope === 'general' ? 'is-active' : ''} onClick={() => { setScope('general'); setBrandFilter('all') }}><Globe2 size={18} /><span><strong>通用内容</strong><small>所有品牌可复用</small></span></button>
      <button type="button" role="tab" aria-selected={scope === 'brand'} className={scope === 'brand' ? 'is-active' : ''} onClick={() => setScope('brand')}><LockKeyhole size={18} /><span><strong>品牌专属</strong><small>按品牌隔离使用</small></span></button>
      <button type="button" role="tab" aria-selected={scope === 'subjects'} className={scope === 'subjects' ? 'is-active' : ''} onClick={() => setScope('subjects')}><Package size={18} /><span><strong>历史主体</strong><small>视频主体资产</small></span></button>
    </div>

    {scope !== 'subjects' ? <div className="library-toolbar">
      <div className="library-tabs" role="tablist" aria-label={`${scope === 'general' ? '通用' : '品牌专属'}内容类型`}>
        <button type="button" role="tab" aria-selected={kind === 'actions'} className={kind === 'actions' ? 'is-active' : ''} onClick={() => setKind('actions')}><Activity size={17} />动作库<span>{scope === 'general' ? generalActionCount : brandActionCount}</span></button>
        <button type="button" role="tab" aria-selected={kind === 'styles'} className={kind === 'styles' ? 'is-active' : ''} onClick={() => setKind('styles')}><Clapperboard size={17} />风格库<span>{scope === 'general' ? generalStyleCount : brandStyleCount}</span></button>
      </div>
      <div className="library-toolbar-actions">
        {scope === 'brand' ? <label className="library-filter"><span>品牌</span><select value={brandFilter} onChange={(event) => setBrandFilter(event.target.value)}><option value="all">全部品牌</option>{[...brandNames].map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></label> : null}
        {tab === 'actions' ? <label className="library-filter"><span>分类</span><select value={category} onChange={(event) => setCategory(event.target.value as ActionCategoryFilter)}><option value="all">全部分类</option>{Object.entries(ACTION_CATEGORY_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label> : <span className="library-safety-note"><ShieldCheck size={16} />草稿风格不会自动进入付费生产</span>}
        {canEditCatalog ? <button type="button" className="primary-button library-add-button" onClick={() => setEditor({ kind: tab === 'actions' ? 'action' : 'style', initialScope: scope })}><Plus size={16} />新增{scope === 'brand' ? '品牌' : '通用'}{tab === 'actions' ? '动作' : '风格'}</button> : null}
      </div>
    </div> : null}

    {tab !== 'subjects' && loading ? <div className="library-loading" role="status"><LoaderCircle className="spin" size={22} /><span>正在读取内容库</span></div> : null}
    {tab !== 'subjects' && error ? <div className="inline-alert inline-alert--danger library-error" role="alert"><AlertTriangle size={17} /><span>{error}</span></div> : null}

    {!loading && !error && tab === 'actions' ? <section className="action-library-grid" aria-label="动作提示词列表">
      {visibleActions.map((action) => <article className="action-library-card" key={action.id}>
        <header>
          <div className="library-card-labels"><span className={`action-category action-category--${action.category}`}>{ACTION_CATEGORY_LABELS[action.category]}</span>{action.brandId ? <span className="library-brand-label"><LockKeyhole size={11} />{brandNames.get(action.brandId) ?? action.brandId}</span> : null}</div>
          <span className={action.riskLevel === 'conditional' ? 'library-status library-status--warning' : 'library-status'}>{action.riskLevel === 'conditional' ? '需满足前提' : '低风险'}</span>
        </header>
        <div className="action-card-title"><div><h2>{action.label}</h2><code>{action.id}</code></div><span className="library-card-actions">{canEditCatalog ? <button type="button" className="icon-button" onClick={() => setEditor({ kind: 'action', item: action })} aria-label={`编辑${action.label}`} title="编辑动作"><Pencil size={16} /></button> : null}<button type="button" className="icon-button" onClick={() => void copyAction(action)} aria-label={`复制${action.label}提示词`} title="复制提示词">{copiedActionId === action.id ? <Check size={17} /> : <Copy size={17} />}</button></span></div>
        {action.baseActionId ? <p className="library-inheritance"><ChevronRight size={14} />基于通用动作：{actionNames.get(action.baseActionId) ?? action.baseActionId}</p> : null}
        <p className="action-instruction">{action.instruction}</p>
        <div className="action-purpose"><span>商品目的</span><p>{action.purpose}</p></div>
        <div className="library-chip-group"><span>适用模板</span><div>{action.compatibleTemplates.map((id) => <i key={id}>{templateNames.get(id) ?? id}</i>)}</div></div>
        {action.requirements.length || action.avoid.length ? <details className="library-details"><summary>使用前提与避坑<ChevronRight size={16} /></summary><div>{action.requirements.length ? <section><strong>使用前提</strong><ul>{action.requirements.map((item) => <li key={item}>{item}</li>)}</ul></section> : null}{action.avoid.length ? <section><strong>避免</strong><ul>{action.avoid.map((item) => <li key={item}>{item}</li>)}</ul></section> : null}</div></details> : null}
      </article>)}
    </section> : null}

    {!loading && !error && tab === 'styles' ? <section className="style-library-grid" aria-label="站点视频风格列表">
      {visibleProfiles.map((profile) => {
        const status = styleStatus(profile)
        return <article className="style-library-card" key={profile.id}>
        <header>
          <div><span className={status.warning ? 'library-status library-status--warning' : 'library-status library-status--verified'}>{status.label}</span><span className="library-version">{profile.version}</span></div>
          {canEditCatalog ? <button type="button" className="secondary-button library-edit-button" onClick={() => setEditor({ kind: 'style', item: profile })}><Pencil size={15} />编辑风格</button> : null}
        </header>
        <div className="style-card-title"><div><h2>{profile.name}</h2><p>{profile.tone}</p></div><span className="style-card-mark"><Clapperboard size={20} /></span></div>
        <div className="style-expression"><span title="人物表达"><UserRound size={15} /></span><p>{profile.expressionLanguage}</p></div>
        <div className="style-grammar">
          <div><span>开</span><p>{profile.openingRule}</p></div>
          <div><span>承</span><p>{profile.middleRule}</p></div>
          <div><span>收</span><p>{profile.endingRule}</p></div>
        </div>
        <div className="style-camera"><span>镜头触感</span><p>{profile.cameraLanguage}</p><small>{profile.pacing}</small></div>
        <details className="library-details style-library-details"><summary>镜头、动作与商品规则<ChevronRight size={16} /></summary><div>
          <section><strong>适用受众</strong><p>{profile.audience}</p></section>
          <section><strong>视觉语言</strong><p>{profile.typography}</p>{profile.palette.length ? <div className="detail-chip-row">{profile.palette.map((item) => <i key={item}>{item}</i>)}</div> : null}</section>
          <section><strong>优先镜头</strong><div className="detail-chip-row">{profile.preferredShots.map((item) => <i key={item}>{item}</i>)}</div></section>
          <section><strong>关联动作</strong><div className="detail-chip-row">{profile.preferredActions.map((id) => <i key={id}>{actionNames.get(id) ?? id}</i>)}</div></section>
          <section><strong>商品重点</strong><ul>{profile.productPriorities.map((item) => <li key={item}>{item}</li>)}</ul></section>
          <section className="style-avoid"><strong>禁止错配</strong><ul>{profile.forbiddenMismatches.map((item) => <li key={item}>{item}</li>)}</ul></section>
          <section className="style-evidence"><strong>研究说明</strong><p>{profile.researchNote}</p><small>复核日期 {profile.retrievedAt} · {profile.sourceUrls.length} 条证据来源</small></section>
        </div></details>
      </article>})}
    </section> : null}

    {tab === 'subjects' ? <KlingSubjectsLibrary actorId={actorId} canDelete={canDeleteSubjects} /> : null}

    {!loading && !error && ((tab === 'actions' && !visibleActions.length) || (tab === 'styles' && !visibleProfiles.length)) ? <EmptyState icon={scope === 'brand' ? <LockKeyhole size={24} /> : <Search size={24} />} title={hasActiveLibraryFilters ? '没有匹配内容' : `还没有${scope === 'brand' ? '品牌专属' : '通用'}${tab === 'actions' ? '动作' : '风格'}`} description={hasActiveLibraryFilters ? '换一个关键词或清除筛选后再试。' : canEditCatalog ? `使用右上角按钮新增第一条${tab === 'actions' ? '动作' : '风格'}。` : '当前库尚未录入内容。'} /> : null}
    {editor ? <CatalogEditor target={editor} actions={actions} profiles={profiles} templates={templates} onClose={() => setEditor(null)} onSaved={catalogSaved} /> : null}
  </div>
}

function ProviderCredentials({ adminId }: { adminId: string | null }) {
  const [status, setStatus] = useState<AdminCredentialsStatus | null>(null)
  const [modelKey, setModelKey] = useState('')
  const [modelBaseUrl, setModelBaseUrl] = useState('')
  const [baseUrlError, setBaseUrlError] = useState('')
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
    const modelApiKey = modelKey.trim()
    const normalizedBaseUrl = modelBaseUrl.trim()
    const baseUrlChanged = normalizedBaseUrl !== (status?.modelBaseUrl ?? '')
    const nextBaseUrlError = validateCompatibleBaseUrl(normalizedBaseUrl)
    setBaseUrlError(nextBaseUrlError)
    if (nextBaseUrlError) return
    if (!modelApiKey && !baseUrlChanged) {
      setError('请至少更新一项分析服务配置')
      return
    }
    setBusy(true)
    setError('')
    setSaved(false)
    try {
      const next = await updateAdminCredentials(adminId, {
        ...(modelApiKey ? { modelApiKey } : {}),
        ...(baseUrlChanged && normalizedBaseUrl ? { modelBaseUrl: normalizedBaseUrl } : {}),
        ...(baseUrlChanged && !normalizedBaseUrl ? { clearModelBaseUrl: true } : {}),
      })
      setStatus(next)
      setModelBaseUrl(next.modelBaseUrl ?? '')
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
    modelKey.trim()
    || modelBaseUrl.trim() !== (status?.modelBaseUrl ?? ''),
  )

  return <form className="settings-section credential-section" onSubmit={(event) => void save(event)}>
    <div className="settings-section-heading">
      <div><span>仅管理员</span><h2>分析服务凭据</h2><p>此处只管理方案分析服务；可灵 API Key 请在“可灵官方 API”页维护。密钥只保存在服务端且不会回显。</p></div>
      <button className="primary-button" type="submit" disabled={busy || !hasChanges}>{busy ? <LoaderCircle className="spin" size={16} /> : saved ? <Check size={16} /> : <LockKeyhole size={16} />}{busy ? '正在保存' : saved ? '已安全保存' : '保存配置'}</button>
    </div>
    <div className="credential-grid">
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

function ProviderRoutingSettings({ adminId, onChanged }: { adminId: string; onChanged: () => Promise<void> }) {
  const [currentBackend, setCurrentBackend] = useState<KlingConfig['backend'] | null>(null)
  const [videoBackend, setVideoBackend] = useState<KlingConfig['backend']>('api')
  const [busy, setBusy] = useState<'load' | 'save' | null>('load')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    setBusy('load')
    try {
      const config = await getKlingConfig(adminId)
      setCurrentBackend(config.backend)
      setVideoBackend(config.backend)
      setError('')
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '无法读取生成通道路由')
    } finally { setBusy(null) }
  }, [adminId])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [load])

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (currentBackend === null || currentBackend === videoBackend) return
    setBusy('save')
    setError('')
    setNotice('')
    try {
      const config = await updateKlingConfig(adminId, { backend: videoBackend })
      setCurrentBackend(config.backend)
      setVideoBackend(config.backend)
      setNotice('生成通道路由已更新，仅影响后续新提交的任务。')
      await onChanged()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '生成通道路由切换失败')
    } finally { setBusy(null) }
  }

  const videoHelp = videoBackend === 'api'
    ? '使用可灵官方 API 的模型和视频参数。'
    : videoBackend === 'wavespeed'
      ? '使用下方 WaveSpeed 视频模型和参数。'
      : '使用下方 Bach Image-to-Video 模型和参数。'

  return <form className="settings-section provider-section" onSubmit={(event) => void save(event)}>
    <div className="settings-section-heading">
      <div><span>Provider Routing</span><h2>生成通道路由</h2><p>统一选择图片和视频任务使用的提供商。切换只影响后续新任务，历史任务仍由原提供商查询和下载。</p></div>
      <button className="primary-button" type="submit" disabled={busy !== null || currentBackend === null || currentBackend === videoBackend}>{busy === 'save' ? <LoaderCircle className="spin" size={16} /> : <Check size={16} />}{busy === 'save' ? '正在切换' : '应用通道路由'}</button>
    </div>
    {busy === 'load' && currentBackend === null ? <div className="account-loading"><LoaderCircle className="spin" size={20} />正在读取通道路由…</div> : null}
    {currentBackend !== null ? <div className="kling-settings-grid">
      <label htmlFor="image-provider-route"><strong>图片通道</strong><select id="image-provider-route" value="wavespeed" disabled><option value="wavespeed">WaveSpeed Image API</option></select><small>当前仅接入 WaveSpeed；Bach 图片能力将在 P4 阶段开放。</small></label>
      <label htmlFor="video-provider-route"><strong>视频通道</strong><select id="video-provider-route" value={videoBackend} disabled={busy !== null} onChange={(event) => setVideoBackend(event.target.value as KlingConfig['backend'])}><option value="api">可灵官方 API</option><option value="wavespeed">WaveSpeed 视频 API</option><option value="bach">Bach Image-to-Video</option></select><small>{videoHelp}</small></label>
    </div> : null}
    <div className="kling-provider-feedback" aria-live="polite" aria-atomic="true">{notice ? <p><CheckCircle2 size={15} />{notice}</p> : null}{error ? <div className="inline-alert inline-alert--danger" role="alert"><AlertTriangle size={16} />{error}</div> : null}</div>
  </form>
}

function KlingProviderSettings({ adminId, onChanged }: { adminId: string; onChanged: () => Promise<void> }) {
  const [config, setConfig] = useState<KlingConfig | null>(null)
  const [draft, setDraft] = useState<KlingConfigDraft | null>(null)
  const [status, setStatus] = useState<KlingStatus | null>(null)
  const [busy, setBusy] = useState<'load' | 'save' | 'refresh' | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    setBusy('load')
    try {
      const [nextConfig, nextStatus] = await Promise.all([
        getKlingConfig(adminId),
        getKlingStatus(adminId),
      ])
      setConfig(nextConfig)
      setDraft(createKlingConfigDraft(nextConfig))
      setStatus(nextStatus)
      setError('')
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '无法读取可灵官方 API 配置')
    } finally { setBusy(null) }
  }, [adminId])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [load])

  const updateDraft = <K extends keyof KlingConfigDraft>(field: K, value: KlingConfigDraft[K]) => {
    setDraft((current) => current ? { ...current, [field]: value } : current)
    setError('')
    setNotice('')
  }

  const refreshCapabilities = async () => {
    setBusy('refresh')
    setError('')
    setNotice('')
    try {
      setStatus(await refreshKlingCapabilities(adminId))
      setNotice('官方 API 连接与能力状态已刷新。')
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '验证官方 API 连接失败')
    } finally { setBusy(null) }
  }

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!draft || !config) return
    const validationError = validateKlingConfig(draft, config.apiKeyConfigured)
    if (validationError) {
      setError(validationError)
      setNotice('')
      return
    }
    setBusy('save')
    setError('')
    setNotice('')
    try {
      const next = await updateKlingConfig(adminId, buildKlingConfigPatch(draft))
      setConfig(next)
      setDraft(createKlingConfigDraft(next))
      setNotice('可灵官方 API 配置已保存；后续新任务使用新配置，已提交任务不受影响。')
      await onChanged()
      setStatus(await getKlingStatus(adminId))
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '可灵官方 API 配置保存失败')
    } finally { setBusy(null) }
  }

  const isReady = Boolean(status?.available && status.authenticated)
  const apiState = klingApiStatusPresentation(status?.status, status?.enabled, status?.reason)
  const apiVersion = formatKlingApiVersion(status?.cliVersion)

  const apiKeyWillExist = Boolean(draft?.apiKey.trim()) || Boolean(config?.apiKeyConfigured && !draft?.clearApiKey)
  const hasChanges = Boolean(config && draft && (
    draft.backend !== config.backend
    || draft.baseUrl.trim() !== (config.baseUrl ?? '')
    || draft.callbackUrl.trim() !== (config.callbackUrl ?? '')
    || draft.model !== config.model
    || draft.duration !== config.duration
    || draft.aspectRatio !== config.aspectRatio
    || draft.resolution !== config.resolution
    || draft.audio !== config.audio
    || draft.multiShot !== config.multiShot
    || draft.maxSubmitConcurrency !== config.maxSubmitConcurrency
    || draft.maxPollConcurrency !== config.maxPollConcurrency
    || draft.enabled !== config.enabled
    || draft.apiKey.trim()
    || draft.clearApiKey
  ))

  return <form className="settings-section kling-provider-section" onSubmit={(event) => void save(event)}>
    <div className="settings-section-heading">
      <div><span>可灵官方 API</span><h2>生产生成配置</h2><p>所有新任务固定通过官方 API 提交。密钥、区域和生成参数在保存后立即用于后续任务。</p></div>
      <div className="provider-actions">
        <button className="secondary-button" type="button" disabled={busy !== null || !status?.enabled} onClick={() => void refreshCapabilities()}><RefreshCw className={busy === 'refresh' ? 'spin' : ''} size={16} />验证 API 状态</button>
        <button className="primary-button" type="submit" disabled={busy !== null || !hasChanges}>{busy === 'save' ? <LoaderCircle className="spin" size={16} /> : <Check size={16} />}{busy === 'save' ? '正在保存' : '保存 API 配置'}</button>
      </div>
    </div>

    {busy === 'load' && !draft ? <div className="account-loading"><LoaderCircle className="spin" size={20} />正在读取可灵配置…</div> : null}
    {draft ? <>
      <div className="kling-provider-toolbar">
        <div className="api-status-card">
          <div className="api-status-card-icon"><Clapperboard size={20} /></div>
          <div><small>官方 API 状态{apiVersion ? ` · ${apiVersion}` : ''}</small><strong>{apiState.label}</strong><span>{status ? apiState.message : '正在读取官方 API 状态'}</span></div>
          <span className={`api-status-state is-${apiState.tone}`}>{busy === 'refresh' ? <LoaderCircle className="spin" size={13} /> : isReady ? <CheckCircle2 size={13} /> : <CircleAlert size={13} />}{apiState.label}</span>
        </div>
        <div className="kling-enabled-control">
          <span><strong>启用官方 API</strong><small>{draft.enabled ? '验证通过后新任务可以提交到官方 API' : '新任务不会提交到可灵'}</small></span>
          <label className="settings-switch">
            <input type="checkbox" checked={draft.enabled} disabled={busy !== null} aria-label="启用当前可灵 Provider" onChange={(event) => updateDraft('enabled', event.target.checked)} />
            <span aria-hidden="true" />
          </label>
        </div>
      </div>

      <div className="kling-config-block">
        <div className="kling-config-heading"><div><strong>API 凭据</strong><small>密钥仅发送到服务端保存，页面不会读取或回显原值。</small></div><span className={apiKeyWillExist ? 'is-configured' : 'is-missing'}>{apiKeyWillExist ? '已配置' : '未配置'}</span></div>
        <div className="kling-api-key-row">
          <div className="credential-field">
            <label htmlFor="kling-api-key"><strong>可灵 API Key</strong><small>{config?.apiKeyConfigured && !draft.clearApiKey ? '输入新 Key 将替换现有密钥' : '保存后输入框会自动清空'}</small></label>
            <div className="secret-input"><LockKeyhole size={16} /><input id="kling-api-key" type="password" value={draft.apiKey} onChange={(event) => setDraft((current) => current ? { ...current, apiKey: event.target.value, clearApiKey: false } : current)} placeholder={config?.apiKeyConfigured && !draft.clearApiKey ? '已配置 · 输入新 Key 进行替换' : '输入可灵官方 API Key'} autoComplete="new-password" spellCheck={false} minLength={8} maxLength={4096} aria-describedby="kling-api-key-help" /></div>
            <small id="kling-api-key-help">为安全起见，已保存的 Key 永不回显；留空不会覆盖原值。</small>
          </div>
          <button className="danger-button" type="button" disabled={busy !== null || (!config?.apiKeyConfigured && !draft.apiKey)} onClick={() => setDraft((current) => current ? { ...current, apiKey: '', clearApiKey: !current.clearApiKey } : current)}>{draft.clearApiKey ? <RotateCcw size={15} /> : <X size={15} />}{draft.clearApiKey ? '取消清除' : '清除 API Key'}</button>
        </div>
        {draft.clearApiKey ? <div className="inline-alert inline-alert--warning"><AlertTriangle size={16} />保存后将清除现有 API Key。若仍要启用 API，请先输入新 Key。</div> : null}
      </div>

      <div className="kling-settings-grid">
        <label htmlFor="kling-base-url"><strong>API 区域</strong><select id="kling-base-url" value={draft.baseUrl} disabled={busy !== null} onChange={(event) => updateDraft('baseUrl', event.target.value)}>{KLING_BASE_URL_OPTIONS.map((value) => <option key={value} value={value}>{value.includes('beijing') ? '中国站 · 北京' : '海外站 · 新加坡'}</option>)}</select><small>{draft.baseUrl}</small></label>
        <label htmlFor="kling-callback-url"><strong>回调 URL</strong><input id="kling-callback-url" type="url" value={draft.callbackUrl} disabled={busy !== null} onChange={(event) => updateDraft('callbackUrl', event.target.value)} placeholder="https://example.com/api/kling/callback" autoComplete="url" spellCheck={false} maxLength={2048} /><small>可选；留空时由服务端轮询任务状态</small></label>
        <label htmlFor="kling-model"><strong>模型</strong><select id="kling-model" value={draft.model} disabled={busy !== null} onChange={(event) => updateDraft('model', event.target.value)}>{Array.from(new Set([...KLING_MODEL_OPTIONS, draft.model])).map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
        <label htmlFor="kling-duration"><strong>时长</strong><input id="kling-duration" type="number" min={3} max={15} step={1} value={draft.duration} disabled={busy !== null} onChange={(event) => updateDraft('duration', Number(event.target.value))} /><small>允许范围 3–15 秒</small></label>
        <label htmlFor="kling-aspect-ratio"><strong>画面比例</strong><select id="kling-aspect-ratio" value={draft.aspectRatio} disabled={busy !== null} onChange={(event) => updateDraft('aspectRatio', event.target.value)}>{Array.from(new Set([...KLING_ASPECT_RATIO_OPTIONS, draft.aspectRatio])).map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
        <label htmlFor="kling-resolution"><strong>分辨率</strong><select id="kling-resolution" value={draft.resolution} disabled={busy !== null} onChange={(event) => updateDraft('resolution', event.target.value)}>{Array.from(new Set([...KLING_RESOLUTION_OPTIONS, draft.resolution])).map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
        <label htmlFor="kling-audio"><strong>音频</strong><select id="kling-audio" value={draft.audio} disabled={busy !== null} onChange={(event) => updateDraft('audio', event.target.value)}>{KLING_AUDIO_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
        <label htmlFor="kling-submit-concurrency"><strong>提交并发</strong><input id="kling-submit-concurrency" type="number" min={1} max={20} step={1} value={draft.maxSubmitConcurrency} disabled={busy !== null} onChange={(event) => updateDraft('maxSubmitConcurrency', Number(event.target.value))} /><small>允许范围 1–20</small></label>
        <label htmlFor="kling-poll-concurrency"><strong>查询并发</strong><input id="kling-poll-concurrency" type="number" min={1} max={50} step={1} value={draft.maxPollConcurrency} disabled={busy !== null} onChange={(event) => updateDraft('maxPollConcurrency', Number(event.target.value))} /><small>允许范围 1–50</small></label>
        <label className="kling-inline-switch"><span><strong>多镜头</strong><small>允许模型在一次生成中规划多个镜头</small></span><span className="settings-switch"><input type="checkbox" checked={draft.multiShot} disabled={busy !== null} aria-label="启用可灵多镜头" onChange={(event) => updateDraft('multiShot', event.target.checked)} /><span aria-hidden="true" /></span></label>
      </div>
    </> : null}

    <div className="kling-provider-feedback" aria-live="polite" aria-atomic="true">
      {notice ? <p><CheckCircle2 size={15} />{notice}</p> : null}
      {error ? <div className="inline-alert inline-alert--danger" role="alert"><AlertTriangle size={16} />{error}</div> : null}
    </div>
  </form>
}

function WaveSpeedProviderSettings({ adminId, onChanged }: { adminId: string; onChanged: () => Promise<void> }) {
  const [config, setConfig] = useState<WaveSpeedConfig | null>(null)
  const [draft, setDraft] = useState<WaveSpeedConfigDraft | null>(null)
  const [busy, setBusy] = useState<'load' | 'save' | 'verify' | null>(null)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setBusy('load')
    try {
      const next = normalizeWaveSpeedConfig(await getWaveSpeedConfig(adminId))
      setConfig(next)
      setDraft(createWaveSpeedConfigDraft(next))
      setError('')
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '无法读取 WaveSpeed API 配置')
    } finally { setBusy(null) }
  }, [adminId])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [load])

  const updateDraft = <K extends keyof WaveSpeedConfigDraft>(key: K, value: WaveSpeedConfigDraft[K]) => {
    setDraft((current) => current ? { ...current, [key]: value } : current)
    setNotice('')
    setError('')
  }

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!config || !draft) return
    let parsedUrl: URL
    try { parsedUrl = new URL(draft.baseUrl.trim()) } catch { setError('请输入有效的 WaveSpeed API 根地址。'); return }
    if (!['https:', 'http:'].includes(parsedUrl.protocol)) { setError('WaveSpeed API 地址必须使用 HTTP 或 HTTPS。'); return }
    if (!/^[A-Za-z0-9._-]+(?:\/[A-Za-z0-9._-]+)+$/.test(draft.videoModel.trim())) { setError('请输入有效的 WaveSpeed 视频模型 ID。'); return }
    if (!Number.isInteger(draft.videoDuration) || draft.videoDuration < 3 || draft.videoDuration > 15) { setError('WaveSpeed 视频时长必须是 3-15 秒之间的整数。'); return }
    if (!Number.isInteger(draft.maxSubmitConcurrency) || draft.maxSubmitConcurrency < 1 || draft.maxSubmitConcurrency > 50) { setError('WaveSpeed 提交并发必须是 1-50 之间的整数。'); return }
    if (!Number.isInteger(draft.maxPollConcurrency) || draft.maxPollConcurrency < 1 || draft.maxPollConcurrency > 50) { setError('WaveSpeed 查询并发必须是 1-50 之间的整数。'); return }
    setBusy('save')
    setNotice('')
    setError('')
    try {
      const next = normalizeWaveSpeedConfig(await updateWaveSpeedConfig(adminId, {
        enabled: draft.enabled,
        baseUrl: draft.baseUrl.trim(),
        maxSubmitConcurrency: draft.maxSubmitConcurrency,
        maxPollConcurrency: draft.maxPollConcurrency,
        videoModel: draft.videoModel.trim(),
        videoDuration: draft.videoDuration,
        videoAspectRatio: draft.videoAspectRatio,
        videoSound: draft.videoSound,
        ...(draft.apiKey.trim() ? { apiKey: draft.apiKey.trim() } : {}),
        ...(draft.clearApiKey ? { clearApiKey: true } : {}),
      }))
      setConfig(next)
      setDraft(createWaveSpeedConfigDraft(next))
      setNotice('WaveSpeed API 配置已保存，后续新图片和视频任务将使用新配置。')
      await onChanged()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'WaveSpeed API 配置保存失败')
    } finally { setBusy(null) }
  }

  const verify = async () => {
    setBusy('verify')
    setNotice('')
    setError('')
    try {
      const next = normalizeWaveSpeedConfig(await verifyWaveSpeedConfig(adminId))
      setConfig(next)
      setDraft((current) => current ? {
        ...current,
        enabled: next.enabled,
        baseUrl: next.baseUrl,
        maxSubmitConcurrency: next.maxSubmitConcurrency,
        maxPollConcurrency: next.maxPollConcurrency,
        videoModel: next.videoModel,
        videoDuration: next.videoDuration,
        videoAspectRatio: next.videoAspectRatio,
        videoSound: next.videoSound,
      } : createWaveSpeedConfigDraft(next))
      setNotice('WaveSpeed 连接状态已刷新；验证不会创建图片任务。')
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'WaveSpeed API 连接验证失败')
    } finally { setBusy(null) }
  }

  const credentialLabel = config?.credentialSource === 'admin'
    ? '管理员安全配置'
    : config?.credentialSource === 'environment'
      ? '环境变量配置'
      : '未配置'
  const statusLabel = config?.available ? '连接可用' : config?.enabled ? '等待验证' : '已停用'
  const apiKeyWillExist = Boolean(draft?.apiKey.trim()) || Boolean(config?.apiKeyConfigured && !draft?.clearApiKey)
  const hasChanges = Boolean(config && draft && (
    config.enabled !== draft.enabled
    || config.baseUrl !== draft.baseUrl.trim()
    || config.maxSubmitConcurrency !== draft.maxSubmitConcurrency
    || config.maxPollConcurrency !== draft.maxPollConcurrency
    || config.videoModel !== draft.videoModel.trim()
    || config.videoDuration !== draft.videoDuration
    || config.videoAspectRatio !== draft.videoAspectRatio
    || config.videoSound !== draft.videoSound
    || draft.apiKey.trim()
    || draft.clearApiKey
  ))

  return <form className="settings-section wavespeed-provider-section" onSubmit={(event) => void save(event)}>
    <div className="settings-section-heading">
      <div><span>WaveSpeed AI</span><h2>图片与视频生成 API</h2><p>为图片中心和可切换的视频生产通道提供生成能力。密钥保存后不会在页面回显。</p></div>
      <div className="provider-actions">
        <button className="secondary-button" type="button" disabled={busy !== null || !config?.enabled || !config.apiKeyConfigured} onClick={() => void verify()}><RefreshCw className={busy === 'verify' ? 'spin' : ''} size={16} />验证 API 状态</button>
        <button className="primary-button" type="submit" disabled={busy !== null || !hasChanges}>{busy === 'save' ? <LoaderCircle className="spin" size={16} /> : <Check size={16} />}{busy === 'save' ? '正在保存' : '保存 API 配置'}</button>
      </div>
    </div>

    {busy === 'load' && !draft ? <div className="account-loading"><LoaderCircle className="spin" size={20} />正在读取 WaveSpeed 配置…</div> : null}
    {draft ? <>
      <div className="kling-provider-toolbar">
        <div className="api-status-card">
          <div className="api-status-card-icon"><Images size={20} /></div>
          <div><small>WaveSpeed API 状态</small><strong>{statusLabel}</strong><span>{config?.reason || `凭据来源：${credentialLabel}`}</span></div>
          <span className={`api-status-state is-${config?.available ? 'success' : config?.enabled ? 'warning' : 'neutral'}`}>{busy === 'verify' ? <LoaderCircle className="spin" size={13} /> : config?.available ? <CheckCircle2 size={13} /> : <CircleAlert size={13} />}{statusLabel}</span>
        </div>
        <div className="kling-enabled-control">
          <span><strong>启用 WaveSpeed</strong><small>{draft.enabled ? '验证通过后允许图片中心提交付费任务' : '图片中心不会提交新的 WaveSpeed 任务'}</small></span>
          <label className="settings-switch"><input type="checkbox" checked={draft.enabled} disabled={busy !== null} aria-label="启用 WaveSpeed Provider" onChange={(event) => updateDraft('enabled', event.target.checked)} /><span aria-hidden="true" /></label>
        </div>
      </div>

      <div className="kling-config-block">
        <div className="kling-config-heading"><div><strong>API 凭据</strong><small>新 Key 仅发送到服务端加密保存，GET 和 PATCH 响应均不包含密钥原文。</small></div><span className={apiKeyWillExist ? 'is-configured' : 'is-missing'}>{credentialLabel}</span></div>
        <div className="kling-api-key-row">
          <div className="credential-field">
            <label htmlFor="wavespeed-api-key"><strong>WaveSpeed API Key</strong><small>{config?.apiKeyConfigured && !draft.clearApiKey ? '输入新 Key 将替换当前配置' : '保存后输入框自动清空'}</small></label>
            <div className="secret-input"><LockKeyhole size={16} /><input id="wavespeed-api-key" type="password" value={draft.apiKey} disabled={busy !== null} onChange={(event) => setDraft((current) => current ? { ...current, apiKey: event.target.value, clearApiKey: false } : current)} placeholder={config?.apiKeyConfigured && !draft.clearApiKey ? '已配置 · 输入新 Key 进行替换' : '输入 WaveSpeed API Key'} autoComplete="new-password" spellCheck={false} minLength={8} maxLength={4096} aria-describedby="wavespeed-api-key-help" /></div>
            <small id="wavespeed-api-key-help">留空不会覆盖现有 Key；已保存的 Key 永不回显。</small>
          </div>
          <button className="danger-button" type="button" disabled={busy !== null || (config?.credentialSource !== 'admin' && !draft.apiKey)} onClick={() => setDraft((current) => current ? { ...current, apiKey: '', clearApiKey: !current.clearApiKey } : current)}>{draft.clearApiKey ? <RotateCcw size={15} /> : <X size={15} />}{draft.clearApiKey ? '取消清除' : '清除后台 Key'}</button>
        </div>
        {draft.clearApiKey ? <div className="inline-alert inline-alert--warning"><AlertTriangle size={16} />保存后将清除管理员配置的 Key。环境变量存在时将自动切换到环境变量。</div> : null}
      </div>

      <div className="wavespeed-endpoint-row">
        <label htmlFor="wavespeed-base-url"><strong>API 根地址</strong><div className="secret-input"><Globe2 size={16} /><input id="wavespeed-base-url" type="url" value={draft.baseUrl} disabled={busy !== null} onChange={(event) => updateDraft('baseUrl', event.target.value)} placeholder="https://api.wavespeed.ai/api/v3" autoComplete="url" spellCheck={false} maxLength={2048} /></div><small>由服务端校验并用于后续新任务；已提交任务不受影响。</small></label>
        <dl><dt>凭据来源</dt><dd>{credentialLabel}</dd><dt>服务状态</dt><dd>{config?.status || 'UNKNOWN'}</dd><dt>最近验证</dt><dd>{config?.checkedAt ? new Date(config.checkedAt).toLocaleString('zh-CN') : '尚未验证'}</dd></dl>
      </div>

      <div className="kling-config-block">
        <div className="kling-config-heading"><div><strong>视频生成参数</strong><small>选择 WaveSpeed 视频通道后，新任务使用这里保存的模型与输出规格。</small></div><span className={config?.videoBackendActive ? 'is-configured' : 'is-missing'}>{config?.videoBackendActive ? '当前视频通道' : '备用视频通道'}</span></div>
        <div className="kling-settings-grid">
          <label htmlFor="wavespeed-video-model"><strong>视频模型 ID</strong><input id="wavespeed-video-model" type="text" value={draft.videoModel} disabled={busy !== null} onChange={(event) => updateDraft('videoModel', event.target.value)} placeholder="kwaivgi/kling-video-o3-pro/reference-to-video" spellCheck={false} maxLength={255} /><small>{config?.videoProvider || 'wavespeed_video'}</small></label>
          <label htmlFor="wavespeed-video-duration"><strong>视频时长</strong><input id="wavespeed-video-duration" type="number" min={3} max={15} step={1} value={draft.videoDuration} disabled={busy !== null} onChange={(event) => updateDraft('videoDuration', Number(event.target.value))} /><small>允许范围 3-15 秒</small></label>
          <label htmlFor="wavespeed-video-aspect-ratio"><strong>画面比例</strong><select id="wavespeed-video-aspect-ratio" value={draft.videoAspectRatio} disabled={busy !== null} onChange={(event) => updateDraft('videoAspectRatio', event.target.value)}><option value="9:16">9:16</option><option value="16:9">16:9</option><option value="1:1">1:1</option></select></label>
          <label htmlFor="wavespeed-submit-concurrency"><strong>提交并发</strong><input id="wavespeed-submit-concurrency" type="number" min={1} max={50} step={1} value={draft.maxSubmitConcurrency} disabled={busy !== null} onChange={(event) => updateDraft('maxSubmitConcurrency', Number(event.target.value))} /><small>图片与视频共用</small></label>
          <label htmlFor="wavespeed-poll-concurrency"><strong>查询并发</strong><input id="wavespeed-poll-concurrency" type="number" min={1} max={50} step={1} value={draft.maxPollConcurrency} disabled={busy !== null} onChange={(event) => updateDraft('maxPollConcurrency', Number(event.target.value))} /><small>图片与视频共用</small></label>
          <label className="kling-inline-switch"><span><strong>生成声音</strong><small>请求 WaveSpeed 视频模型生成原生声音</small></span><span className="settings-switch"><input type="checkbox" checked={draft.videoSound} disabled={busy !== null} aria-label="启用 WaveSpeed 视频声音" onChange={(event) => updateDraft('videoSound', event.target.checked)} /><span aria-hidden="true" /></span></label>
        </div>
      </div>
    </> : null}

    <div className="kling-provider-feedback" aria-live="polite" aria-atomic="true">
      {notice ? <p><CheckCircle2 size={15} />{notice}</p> : null}
      {error ? <div className="inline-alert inline-alert--danger" role="alert"><AlertTriangle size={16} />{error}</div> : null}
    </div>
  </form>
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
  const stateLabel = unavailable ? '不可用' : blocked ? '已阻止' : active ? '已开启' : '已关闭'
  return <section className="settings-section prompt-confirmation-section">
    <div className="settings-section-heading">
      <div><span>消息提醒</span><h2>浏览器通知</h2><p>{description}</p></div>
      <div className="prompt-confirmation-control">
        <span className={`prompt-confirmation-state${active ? ' is-active' : ''}`}>{stateLabel}</span>
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
        ? '已开启，普通方案分析完成后将自动开始生成。'
        : '已关闭，后续方案会在生成前等待你确认。')
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '自动确认设置保存失败')
      await load()
    } finally {
      setBusy(false)
    }
  }

  return <section className="settings-section prompt-confirmation-section">
    <div className="settings-section-heading">
      <div><span>生成流程</span><h2>分析完成后自动开始生成</h2><p>{automatic ? '普通方案分析完成后会跳过人工确认并直接生成，可能立即消耗生成额度；需要质量复核或被系统拦截的方案仍需人工处理。' : '默认关闭。分析完成后会停在确认步骤，等你检查提示词并主动开始生成。'}</p></div>
      <div className="prompt-confirmation-control">
        <span className={`prompt-confirmation-state${automatic ? ' is-active' : ''}`}>{busy && !ready ? '读取中' : automatic ? '已开启' : '已关闭'}</span>
        <label className="settings-switch" title="分析完成后自动开始生成">
          <input type="checkbox" checked={automatic} disabled={busy || !ready} aria-label="分析完成后自动开始生成" onChange={(event) => void toggle(event.target.checked)} />
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

function PersonalPasswordSetting() {
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!currentPassword || newPassword.length < 12 || newPassword !== confirmation) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await changePassword(currentPassword, newPassword)
      setCurrentPassword('')
      setNewPassword('')
      setConfirmation('')
      setNotice('密码已修改，其他设备上的旧登录会话已退出。')
    } catch (cause) {
      if (cause instanceof ApiError && cause.code === 'CURRENT_PASSWORD_INVALID') setError('当前密码不正确，请重新输入。')
      else if (cause instanceof ApiError && cause.code === 'PASSWORD_UNCHANGED') setError('新密码不能与当前密码相同。')
      else setError(cause instanceof ApiError ? cause.message : '密码修改失败')
    } finally {
      setBusy(false)
    }
  }

  return <section className="settings-section personal-password-section">
    <div className="settings-section-heading"><div><span>账号安全</span><h2>修改密码</h2><p>修改当前登录账号的密码。保存后，其他设备上的旧登录会话会自动退出。</p></div></div>
    <form className="personal-password-form" onSubmit={(event) => void save(event)}>
      <label htmlFor="settings-current-password"><span>当前密码</span><input id="settings-current-password" type="password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} maxLength={512} autoComplete="current-password" required /></label>
      <label htmlFor="settings-new-password"><span>新密码</span><input id="settings-new-password" type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} minLength={12} maxLength={512} autoComplete="new-password" placeholder="至少 12 个字符" required /></label>
      <label htmlFor="settings-confirm-password"><span>确认新密码</span><input id="settings-confirm-password" type="password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} minLength={12} maxLength={512} autoComplete="new-password" aria-invalid={Boolean(confirmation && confirmation !== newPassword)} required /></label>
      <button className="primary-button" type="submit" disabled={busy || !currentPassword || newPassword.length < 12 || newPassword !== confirmation}>{busy ? <LoaderCircle className="spin" size={16} /> : <KeyRound size={16} />}{busy ? '正在保存' : '保存新密码'}</button>
    </form>
    <div className="account-feedback" aria-live="polite">{notice ? <p><CheckCircle2 size={15} />{notice}</p> : null}{error ? <div className="inline-alert inline-alert--danger" role="alert"><AlertTriangle size={16} />{error}</div> : null}</div>
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
  useEffect(() => {
    localStorage.setItem('generation-provider', 'kling')
    localStorage.removeItem('default-model')
    ;['default-output-variants', 'video-direction', 'default-ratio', 'default-duration', 'max-concurrency', 'retry-count', 'save-directory'].forEach((key) => localStorage.removeItem(key))
  }, [])
  return <div className="page-view settings-view"><div className="page-title"><div><span>个人工作区</span><h1>偏好设置</h1><p>这里只保留会影响你个人工作流的选项；生成模型、API 通道与固定生产规格由管理员统一维护。</p></div><div className="page-title-actions">{system?.sharedAuthentication ? <button className="secondary-button" onClick={onLogout}>退出登录</button> : null}</div></div>
    {system?.sharedAuthentication ? <PersonalPasswordSetting /> : null}
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

function BachProviderSettings({ adminId, onChanged }: { adminId: string; onChanged: () => Promise<void> }) {
  const [config, setConfig] = useState<BachConfig | null>(null)
  const [accessKey, setAccessKey] = useState('')
  const [secretKey, setSecretKey] = useState('')
  const [clearAccessKey, setClearAccessKey] = useState(false)
  const [clearSecretKey, setClearSecretKey] = useState(false)
  const [busy, setBusy] = useState<'load' | 'save' | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    setBusy('load')
    try {
      setConfig(await getBachConfig(adminId))
      setAccessKey('')
      setSecretKey('')
      setClearAccessKey(false)
      setClearSecretKey(false)
      setError('')
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '无法读取 Bach API 配置')
    } finally { setBusy(null) }
  }, [adminId])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [load])

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!config) return
    if (config.enabled && !accessKey.trim() && !config.accessKeyConfigured && (clearAccessKey || !config.accessKeyConfigured)) {
      setError('启用 Bach 前请先填写 AccessKey。')
      return
    }
    if (config.enabled && !secretKey.trim() && !config.secretKeyConfigured && (clearSecretKey || !config.secretKeyConfigured)) {
      setError('启用 Bach 前请先填写 SecretKey。')
      return
    }
    setBusy('save')
    setError('')
    setNotice('')
    const patch: Record<string, unknown> = {}
    patch.enabled = config.enabled
    patch.model = config.model
    patch.resolution = config.resolution
    patch.duration = config.duration
    patch.aspectRatio = config.aspectRatio
    patch.generateAudio = config.generateAudio
    if (accessKey.trim()) patch.accessKey = accessKey.trim()
    if (secretKey.trim()) patch.secretKey = secretKey.trim()
    if (clearAccessKey) patch.clearAccessKey = true
    if (clearSecretKey) patch.clearSecretKey = true
    try {
      const next = await updateBachConfig(adminId, patch)
      setConfig(next)
      setAccessKey('')
      setSecretKey('')
      setClearAccessKey(false)
      setClearSecretKey(false)
      setNotice('Bach AK/SK 配置已安全保存；选择 Bach 通道后用于后续新任务。')
      await onChanged()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Bach API 配置保存失败')
    } finally { setBusy(null) }
  }

  return <form className="settings-section provider-section" onSubmit={(event) => void save(event)}>
    <div className="settings-section-heading">
      <div><span>Bach API · P1</span><h2>首尾帧视频配置</h2><p>AK/SK 只发送到服务端并加密保存，页面不会读取或回显原值。当前阶段接入 Image-to-Video。</p></div>
      <button className="primary-button" type="submit" disabled={busy !== null || !config}>{busy === 'save' ? <LoaderCircle className="spin" size={16} /> : <LockKeyhole size={16} />}{busy === 'save' ? '正在保存' : '保存 Bach 配置'}</button>
    </div>
    {busy === 'load' && !config ? <div className="account-loading"><LoaderCircle className="spin" size={20} />正在读取 Bach 配置…</div> : null}
    {config ? <>
      <div className="kling-provider-toolbar">
        <div className="api-status-card">
          <div className="api-status-card-icon"><Clapperboard size={20} /></div>
          <div><small>Bach 凭据状态</small><strong>{config.credentialsConfigured ? '已配置' : '未配置'}</strong><span>{config.credentialsConfigured ? '保存后可在上方通道选择中启用 Bach。' : '请填写 AccessKey 和 SecretKey。'}</span></div>
          <span className={`api-status-state is-${config.credentialsConfigured ? 'success' : 'warning'}`}>{config.credentialsConfigured ? <CheckCircle2 size={13} /> : <CircleAlert size={13} />}{config.credentialsConfigured ? '已配置' : '待配置'}</span>
        </div>
        <div className="kling-enabled-control"><span><strong>启用 Bach</strong><small>{config.enabled ? '允许后续任务使用 Bach' : '新任务不会提交到 Bach'}</small></span><label className="settings-switch"><input type="checkbox" checked={config.enabled} onChange={(event) => setConfig((current) => current ? { ...current, enabled: event.target.checked } : current)} aria-label="启用 Bach Provider" /><span aria-hidden="true" /></label></div>
      </div>
      <div className="kling-api-key-row">
        <div className="credential-field"><label htmlFor="bach-access-key"><strong>AccessKey</strong><small>{config.accessKeyConfigured && !clearAccessKey ? '已配置 · 输入新 AK 可替换' : '保存后输入框自动清空'}</small></label><div className="secret-input"><LockKeyhole size={16} /><input id="bach-access-key" type="password" value={accessKey} onChange={(event) => { setAccessKey(event.target.value); setClearAccessKey(false) }} placeholder={config.accessKeyConfigured && !clearAccessKey ? '已配置 · 输入新 AK 进行替换' : '输入 Bach AccessKey'} autoComplete="new-password" spellCheck={false} minLength={8} maxLength={4096} /></div><small>仅服务端保存，读取接口只返回是否已配置。</small></div>
        <button className="danger-button" type="button" disabled={busy !== null || (!config.accessKeyConfigured && !accessKey)} onClick={() => setClearAccessKey((value) => !value)}>{clearAccessKey ? <RotateCcw size={15} /> : <X size={15} />}{clearAccessKey ? '取消清除 AK' : '清除 AK'}</button>
      </div>
      <div className="kling-api-key-row">
        <div className="credential-field"><label htmlFor="bach-secret-key"><strong>SecretKey</strong><small>{config.secretKeyConfigured && !clearSecretKey ? '已配置 · 输入新 SK 可替换' : '保存后输入框自动清空'}</small></label><div className="secret-input"><LockKeyhole size={16} /><input id="bach-secret-key" type="password" value={secretKey} onChange={(event) => { setSecretKey(event.target.value); setClearSecretKey(false) }} placeholder={config.secretKeyConfigured && !clearSecretKey ? '已配置 · 输入新 SK 进行替换' : '输入 Bach SecretKey'} autoComplete="new-password" spellCheck={false} minLength={8} maxLength={4096} /></div><small>SecretKey 不会进入浏览器、日志或普通配置响应。</small></div>
        <button className="danger-button" type="button" disabled={busy !== null || (!config.secretKeyConfigured && !secretKey)} onClick={() => setClearSecretKey((value) => !value)}>{clearSecretKey ? <RotateCcw size={15} /> : <X size={15} />}{clearSecretKey ? '取消清除 SK' : '清除 SK'}</button>
      </div>
      <div className="kling-settings-grid">
        <label><strong>模型</strong><input value={config.model} readOnly /></label>
        <label><strong>分辨率</strong><select value={config.resolution} onChange={(event) => setConfig((current) => current ? { ...current, resolution: event.target.value } : current)}><option value="720p">720p</option><option value="1080p">1080p</option></select></label>
        <label><strong>时长</strong><input type="number" min={1} max={8} value={config.duration} onChange={(event) => setConfig((current) => current ? { ...current, duration: Number(event.target.value) } : current)} /><small>首帧 1–8 秒；首尾帧 1–6 秒</small></label>
        <label><strong>画面比例</strong><select value={config.aspectRatio} onChange={(event) => setConfig((current) => current ? { ...current, aspectRatio: event.target.value } : current)}><option value="9:16">9:16</option><option value="16:9">16:9</option><option value="1:1">1:1</option></select></label>
        <label className="kling-inline-switch"><span><strong>生成音频</strong><small>仅在 Bach 任务 payload 中启用音频</small></span><span className="settings-switch"><input type="checkbox" checked={config.generateAudio} onChange={(event) => setConfig((current) => current ? { ...current, generateAudio: event.target.checked } : current)} /><span aria-hidden="true" /></span></label>
      </div>
    </> : null}
    <div className="kling-provider-feedback" aria-live="polite" aria-atomic="true">{notice ? <p><CheckCircle2 size={15} />{notice}</p> : null}{error ? <div className="inline-alert inline-alert--danger" role="alert"><AlertTriangle size={16} />{error}</div> : null}</div>
  </form>
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
  const activeVideo = system?.videoGeneration ?? system?.kling
  const activeProvider = providerPresentation(activeVideo?.provider)
  const providerStateLabel = activeVideo?.available && activeVideo.authenticated
    ? '已就绪'
    : activeVideo?.enabled ? '待验证' : '未启用'
  const environmentLabel = system?.environment === 'production'
    ? '正式生产'
    : system?.environment === 'staging'
      ? '预发布'
      : system?.environment === 'test'
        ? '测试环境'
        : '开发环境'
  const sections: Array<{ value: AdminSection; label: string; description: string; icon: React.ReactNode }> = [
    { value: 'overview', label: '运行总览', description: '生产开关、队列与告警', icon: <Activity size={17} /> },
    ...(isAdmin ? [{ value: 'accounts' as const, label: '成员账号', description: '创建、重置与停用', icon: <UserRound size={17} /> }] : []),
    { value: 'providers', label: '生成提供商', description: '视频与图片 API 配置', icon: <Clapperboard size={17} /> },
    { value: 'security', label: '流程与分析', description: '确认策略和分析服务', icon: <KeyRound size={17} /> },
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
    <ErrorBoundary resetKeys={[section]} onBack={() => onSectionChange('overview')} backLabel="返回运行总览">
    <div className="admin-section-content" key={section}>
      {section === 'overview' ? <>
        <section className="admin-summary-grid" aria-label="系统摘要">
          <div><span className="summary-icon summary-icon--blue"><LayoutDashboard size={19} /></span><span><small>运行环境</small><strong>{environmentLabel}</strong></span></div>
          <div><span className={`summary-icon ${activeVideo?.available && activeVideo.authenticated ? 'summary-icon--green' : 'summary-icon--amber'}`}><Activity size={19} /></span><span><small>{activeProvider.displayLabel}</small><strong>{providerStateLabel}</strong></span></div>
          <div><span className="summary-icon summary-icon--green"><Clapperboard size={19} /></span><span><small>生成模型</small><strong>{activeVideo?.model || activeVideo?.models[0] || '待配置'}</strong></span></div>
        </section>
        <section className="settings-section admin-operations-card"><OperationsPanel adminId={actor?.userId ?? null} /></section>
      </> : null}
      {section === 'accounts' && isAdmin ? <UserManagement adminId={actor!.userId} sharedAuthentication={system?.sharedAuthentication ?? false} /> : null}
      {section === 'providers' ? isAdmin ? <>
        <ProviderRoutingSettings key={`routing-${activeVideo?.backend ?? 'unknown'}`} adminId={actor!.userId} onChanged={onKlingChanged} />
        <KlingProviderSettings key={`kling-${activeVideo?.backend ?? 'unknown'}`} adminId={actor!.userId} onChanged={onKlingChanged} />
        <WaveSpeedProviderSettings key={`wavespeed-${activeVideo?.backend ?? 'unknown'}`} adminId={actor!.userId} onChanged={onKlingChanged} />
        <BachProviderSettings key={`bach-${activeVideo?.backend ?? 'unknown'}`} adminId={actor!.userId} onChanged={onKlingChanged} />
      </> : <EmptyState icon={<ShieldCheck size={24} />} title="需要管理员权限" description="生成提供商的密钥、端点与连接验证仅允许管理员修改。" /> : null}
      {section === 'security' ? <>
        <PromptConfirmationSetting adminId={actor!.userId} />
        {isAdmin ? <ProviderCredentials adminId={actor!.userId} /> : <EmptyState icon={<KeyRound size={24} />} title="凭据由管理员维护" description="你仍可管理生产确认流程，但不能查看或修改服务凭据。" />}
      </> : null}
    </div>
    </ErrorBoundary>
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
  const [imageComposerSeed, setImageComposerSeed] = useState<RemixSeed | null>(null)
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
  const [inPageTaskToasts, setInPageTaskToasts] = useState<InPageTaskToast[]>([])
  const [hasActiveImageTasks, setHasActiveImageTasks] = useState(false)
  const [imageNotificationTaskId, setImageNotificationTaskId] = useState<string | null>(null)
  const previousTaskPhasesRef = useRef<Map<string, string>>(new Map())
  const notificationBaselineReadyRef = useRef(false)
  const activeNotificationsRef = useRef<Map<string, Notification>>(new Map())
  const notificationAudioContextRef = useRef<AudioContext | null>(null)
  const pendingImageVideoSeedsRef = useRef<RemixSeed[]>([])
  const pendingImageSelectionClearRef = useRef<(() => void) | null>(null)

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
  }, [browserNotificationsEnabled, navigate, notificationPermission, playTaskNotificationSound])

  const handleImageNotifications = useCallback((events: ImageCenterNotificationEvent[]) => {
    presentTaskNotifications(events.map(({ taskId, status, notification }) => ({
      notificationKey: `image:${taskId}`,
      taskId,
      view: 'images',
      payload: notification,
      tone: status === 'completed' ? 'success' : 'warning',
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

  const selectedTask = tasks.find((task) => task.id === detailId) ?? null
  const counts = useMemo(() => ({
    attention: tasks.filter((task) => task.phase === 'AWAITING_CONFIRMATION').length,
    active: tasks.filter((task) => ACTIVE_PHASES.has(task.phase)).length,
  }), [tasks])
  const showNotificationPrompt = browserNotificationsEnabled
    && notificationPermission === 'default'
    && !notificationPromptDismissed
    && (hasActiveImageTasks || tasks.some((task) => ACTIVE_PHASES.has(task.phase) || task.phase === 'AWAITING_CONFIRMATION'))

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
  const prepareImageCenterVideos = async (handoffs: ImageCenterVideoHandoff[], onSubmitted: () => void) => {
    if (!handoffs.length) return
    setError('')
    try {
      const seeds = await Promise.all(handoffs.map(async ({ task, outputs, subjectSource }) => {
        const storyboards = await Promise.all(outputs.slice(0, 6).map((output, index) => imageCenterOutputFile(output, task.outfitName, index)))
        const selectedSubject = subjectSource === 'product-front'
          ? task.product.front
          : subjectSource === 'product-back'
            ? task.product.back
            : storyboards[0]
        if (!selectedSubject) throw new Error(`“${task.outfitName}”缺少可用主体图。`)
        return createImageCenterVideoSeed(task, storyboards, selectedSubject, createUuid())
      }))
      pendingImageVideoSeedsRef.current = seeds.slice(1)
      pendingImageSelectionClearRef.current = onSubmitted
      setImageComposerSeed(seeds[0])
    } catch (cause) {
      throw new Error(cause instanceof Error ? cause.message : '无法准备图片中心的视频素材', { cause })
    }
  }
  const play = (task: Task, variant: Variant) => {
    if (!variant.downloadArtifactId) { navigate('make', task.id); return }
    setVideo({ artifactId: variant.downloadArtifactId, title: `${task.title} · ${variantDisplayName(variant)}` })
  }
  const created = useCallback((task: Task, open = false) => {
    setTasks((current) => [task, ...current.filter((item) => item.id !== task.id)])
    const nextSeed = pendingImageVideoSeedsRef.current.shift() ?? null
    setSeed(nextSeed)
    if (open) navigate('make', task.id)
    else if (nextSeed) navigate('make')
  }, [navigate])
  const imageComposerCreated = useCallback((task: Task) => {
    setTasks((current) => [task, ...current.filter((item) => item.id !== task.id)])
    pendingImageSelectionClearRef.current?.()
    pendingImageSelectionClearRef.current = null
    const nextSeed = pendingImageVideoSeedsRef.current.shift() ?? null
    setImageComposerSeed(nextSeed)
  }, [])
  const closeImageComposer = () => {
    pendingImageVideoSeedsRef.current = []
    pendingImageSelectionClearRef.current = null
    setImageComposerSeed(null)
  }
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

  if (loading && !actor && !authRequired) {
    return <main className="app-boot-screen"><div role="status" aria-label="正在连接生产服务"><LoaderCircle className="spin" size={22} /></div></main>
  }

  const canOperate = actor?.role === 'ADMIN' || actor?.role === 'OPERATOR'
  const currentVideoGeneration = system?.videoGeneration ?? system?.kling
  const currentProviderLabel = system
    ? providerPresentation(currentVideoGeneration?.provider).displayLabel
    : 'AI 视频生产'
  const nav: Array<{ value: View; label: string; icon: React.ReactNode; badge?: number }> = [
    { value: 'images', label: '图片中心', icon: <Images size={18} /> },
    { value: 'make', label: '视频制作', icon: <Plus size={18} /> },
    { value: 'records', label: '任务', icon: <ListVideo size={18} />, badge: counts.attention || counts.active },
    { value: 'library', label: '内容库', icon: <Library size={18} /> },
    ...(canOperate ? [{ value: 'admin' as const, label: '管理', icon: <ShieldCheck size={18} /> }] : []),
    { value: 'settings', label: '设置', icon: <Settings size={18} /> },
  ]
  const mobileNav = nav.filter((item) => item.value !== 'admin')
  if (system?.sharedAuthentication && authRequired) {
    return <LoginScreen onAuthenticated={async () => { setLoading(true); await refresh() }} />
  }
  return <div className="app-shell">
    <a className="skip-link" href="#main-content">跳到主要内容</a>
    <aside className="sidebar">
      <ProductLogo subtitle={currentProviderLabel} />
      <nav className="sidebar-main-nav" aria-label="主导航">{nav.filter((item) => item.value !== 'settings').map((item) => <button key={item.value} onClick={() => switchView(item.value)} className={view === item.value ? 'is-active' : ''}>{item.icon}<span>{item.label}</span>{item.badge ? <i>{item.badge}</i> : null}</button>)}</nav>
      <div className="sidebar-bottom">
        <div className="sidebar-status"><span className={error ? 'is-offline' : ''} /><span>{error ? '服务连接异常' : system?.environment === 'test' ? '测试版' : '正式版'}</span></div>
        <button className={`sidebar-settings ${view === 'settings' ? 'is-active' : ''}`} onClick={() => switchView('settings')}><Settings size={18} /><span>设置</span></button>
        <div className="sidebar-utility"><button onClick={() => setSidebarInfo((current) => current === 'help' ? null : 'help')} aria-label="帮助" title="帮助"><HelpCircle size={17} /></button><button onClick={() => setSidebarInfo((current) => current === 'account' ? null : 'account')} aria-label="账号" title="账号"><UserRound size={17} /></button></div>
        {sidebarInfo ? <div className="sidebar-popover" role="status"><strong>{sidebarInfo === 'help' ? '制作帮助' : '当前账号'}</strong><p>{sidebarInfo === 'help' ? '上传服装与参考图后，确认方案即可开始生成。历史视频可在记录中继续处理。' : `${actor?.username ?? '生产账号'} · ${actor?.role === 'ADMIN' ? '管理员' : actor?.role === 'OPERATOR' ? '运营人员' : '普通用户'}`}</p>{sidebarInfo === 'account' && system?.sharedAuthentication ? <button onClick={() => void signOut()}>退出登录</button> : sidebarInfo === 'account' && system?.phaseOneAdminId ? <button onClick={switchDevelopmentActor}>切换为{devActorRole === 'admin' ? '普通用户' : '管理员'}</button> : <button onClick={() => setSidebarInfo(null)}>关闭</button>}</div> : null}
      </div>
    </aside>
    <div className="app-body">
      <header className="mobile-topbar"><ProductLogo subtitle={currentProviderLabel} /><div className="service-state"><span className={error ? 'is-offline' : ''} />{error ? '服务异常' : system?.environment === 'test' ? '测试版' : '正式版'}</div></header>
      <main id="main-content"><ErrorBoundary resetKeys={[view, adminSection, selectedTask?.id]} onBack={() => navigate('make')} backLabel="返回制作页">{loading ? <div className="page-loading"><LoaderCircle className="spin" size={26} /><strong>正在加载生产任务</strong></div> : <>
      {error ? <div className="service-banner"><AlertTriangle size={18} /><span>{error}</span><button onClick={() => void refresh()}><RefreshCw size={15} />重新连接</button></div> : null}
      {showNotificationPrompt ? <div className="notification-permission-banner" role="region" aria-label="浏览器通知">
        <Bell size={18} />
        <span><strong>后台进度提醒</strong><small>开启通知，图片或视频完成、异常以及方案待确认时会及时提醒你。</small></span>
        <button className="secondary-button" type="button" onClick={() => void enableBrowserNotifications()}>开启通知</button>
        <button className="icon-button" type="button" aria-label="暂不开启通知" title="暂不开启" onClick={() => setNotificationPromptDismissed(true)}><X size={17} /></button>
      </div> : null}
      <ImageCenter
        active={view === 'images'}
        openTaskId={imageNotificationTaskId}
        onPrepareVideos={prepareImageCenterVideos}
        onNotifications={handleImageNotifications}
        onActiveTasksChange={setHasActiveImageTasks}
      />
      <HomeView active={view === 'make' && !selectedTask} tasks={tasks} seed={seed} system={system} actorId={system?.sharedAuthentication ? null : actor?.userId ?? null} onCreated={created} onOpen={(task) => navigate('make', task.id)} onView={switchView} onPlay={play} onRemix={(task) => void remix(task)} onFeedbackChanged={feedbackChanged} />
      {view === 'make' && selectedTask ? <ProductionWorkspace key={`${selectedTask.id}-${selectedTask.phase}`} task={selectedTask} onClose={() => navigate('make')} onChanged={taskChanged} onRemix={() => void remix(selectedTask)} onReuse={(variants) => void reuseCompleted(selectedTask, variants)} onPlay={(variant) => play(selectedTask, variant)} /> : null}
      {view === 'records' ? <RecordsView tasks={tasks} hasMore={Boolean(nextTaskCursor)} loadingMore={loadingMoreTasks} onLoadMore={() => void loadMoreTasks()} onOpen={(task) => navigate('make', task.id)} onPlay={play} onRemix={(task) => void remix(task)} onFeedbackChanged={feedbackChanged} /> : null}
      {view === 'library' ? <ContentLibraryView
        actorId={system?.sharedAuthentication ? null : actor?.userId ?? null}
        canDeleteSubjects={actor?.role === 'ADMIN'}
        canEditCatalog={Boolean(actor)}
      /> : null}
      {view === 'admin' ? <AdminCenterView system={system} actor={actor} section={adminSection} onSectionChange={(section) => navigate('admin', null, false, section)} onKlingChanged={refresh} /> : null}
      {view === 'settings' ? <SettingsView
        system={system}
        onLogout={() => void signOut()}
        browserNotificationsEnabled={browserNotificationsEnabled}
        browserNotificationPermission={notificationPermission}
        onEnableBrowserNotifications={enableBrowserNotifications}
        onDisableBrowserNotifications={disableBrowserNotifications}
      /> : null}
      </>}</ErrorBoundary></main>
    </div>
    <nav className="mobile-nav" aria-label="移动端主导航" style={{ gridTemplateColumns: `repeat(${mobileNav.length}, minmax(0, 1fr))` }}>{mobileNav.map((item) => <button key={item.value} onClick={() => switchView(item.value)} className={view === item.value ? 'is-active' : ''}>{item.icon}<span>{item.label}</span>{item.badge ? <i>{item.badge}</i> : null}</button>)}</nav>
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
    {imageComposerSeed ? <ImageVideoComposerSheet seed={imageComposerSeed} system={system} actorId={system?.sharedAuthentication ? null : actor?.userId ?? null} onClose={closeImageComposer} onCreated={imageComposerCreated} /> : null}
    {remixStage ? <div className="global-loading"><LoaderCircle className="spin" size={20} /><span>{remixStage === 'reuse' ? '正在复用素材和提示词并提交生成' : '正在加载原素材'}</span></div> : null}
  </div>
}

export default App
