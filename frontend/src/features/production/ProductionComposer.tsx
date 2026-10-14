// 本文件由 App.tsx 拆分生成（2026-09-28 前端架构拆分 v2）。
import { AlertTriangle, ArrowRight, Check, CheckCircle2, ChevronRight, CircleAlert, Images, LoaderCircle, LockKeyhole, Settings, UploadCloud, WandSparkles } from 'lucide-react'
import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { ApiError, createVideoTask, getKlingElements, getSiteStyleProfiles, getVideoTemplates, querySubmissionRecovery, uploadStoryboard, type SubmissionRecoveryResult } from '../../api'
import { mapWithConcurrency } from '../../concurrency'
import { type KlingElement, type SiteStyleProfileSummary, type SystemStatus, type Task, type VideoTemplateSummary } from '../../types'
import { CustomPromptField } from '../../CustomPromptField'
import { SubjectInputPanel } from '../../SubjectInputPanel'
import { IMAGE_FILE_ACCEPT, isSupportedImageFile } from '../../imageFiles'
import { type BatchUploadGroup, groupBatchUploadFiles } from '../../batchUpload'
import { type SubjectInputMode, type SubjectReferenceFiles, buildSubjectImageReferences, createEmptySubjectReferenceFiles, getSubjectReferenceCount, validateSubjectReferenceFiles } from '../../subjectFiles'
import { createUuid } from '../../uuid'
import { providerPresentation } from '../../providerPresentation'
import { loadVideoComposerSettings, saveVideoComposerSettings } from '../../videoComposerSettings'
import { formatVideoDurationOptions, getVideoDurationOptions, normalizeVideoDuration } from '../../videoDurationOptions'
import { type DirectorFixedPreparation, type Material, type RemixSeed, type UploadBucket, UPLOAD_CONCURRENCY } from './productionTypes'
import { MATERIAL_DRAG_TYPE, MaterialCard } from './MaterialCard'
import { formatTime } from '../../domain/taskPresentation'
import { ImagePreview } from '../../shared/components/Media'
import { SourceInspector } from '../../shared/components/studio/SourceInspector'
import { Storyboard } from '../../shared/components/studio/Storyboard'
import { TemplateSelector } from '../../shared/components/studio/TemplateSelector'
import { SubjectDisclosure } from '../../shared/components/studio/SubjectDisclosure'
import { Button } from '../../shared/components/ui/Button'
import { ImageUploadTrigger } from '../../shared/components/studio/ImageUploadTrigger'
import './videoStudio.css'
import './studioRefinement.css'

/**
 * 维护模式是计划内的服务状态，不是用户操作错误。全站只保留这一条口径（评审 V2）：
 * 其余位置（模板下拉、站点风格下拉、提示词方案行）只显示最短占位「不可用」，不再重复解释。
 */
const MAINTENANCE_MESSAGE = '当前处于维护模式，已有任务仍可查看，生成暂不可用。'

/** 「重新读取」的最小可见时长：接口在维护模式下会瞬间返回，没有这个下限就看不到任何反馈（评审 I4）。 */
const CATALOG_RELOAD_MIN_VISIBLE_MS = 600

function DirectorFixedPreparationPanel({ preparation }: { preparation: DirectorFixedPreparation }) {
  const input = preparation.input
  const hash = preparation.sourceImageHash
  return <section
    className="composer composer--studio"
    aria-label="导演固定视频准备"
    data-execution-mode="director_fixed"
    data-provider-submission-allowed="false"
  >
    <div className="generation-workflow-heading">
      <div>
        <span>Video Studio / Director Fixed</span>
        <h2>导演视频准备</h2>
      </div>
      <strong>{preparation.status === 'READY' ? '只读准备完成' : '等待补齐 handoff'}</strong>
    </div>
    <div className="inline-alert" role="status">
      <LockKeyhole size={17} />
      <span>
        <strong>OFFLINE_SYNTHETIC_ONLY · 不可交付</strong>
        <small>当前只做不可变输入摘要和 preflight 展示，不上传、不调用 Provider、不创建真实视频任务。</small>
      </span>
    </div>
    <dl className="director-package-list">
      <div><dt>creative_task_id</dt><dd>{preparation.creativeTaskId ?? '未提供'}</dd></div>
      <div><dt>package / revision</dt><dd>{preparation.packageId ?? '未提供'}{preparation.packageRevision ? ` · r${preparation.packageRevision}` : ''}</dd></div>
      <div><dt>shot_id</dt><dd>{preparation.shotId ?? '需要 SHOT_01'}</dd></div>
      <div><dt>candidate_id</dt><dd>{preparation.candidateId ?? '未提供'}</dd></div>
      <div><dt>source image hash</dt><dd><code>{hash ?? '未提供'}</code></dd></div>
      <div><dt>shot mapping</dt><dd>{input?.shotMapping.outputId ?? input?.shotMapping.objectKey ?? (preparation.shotMapping ? '已提供摘要' : '未提供')}</dd></div>
    </dl>
    {preparation.preflight ? <div className="inline-alert" role="status">
      <CircleAlert size={17} />
      <span><strong>只读 preflight：{preparation.preflight.readiness.score}%</strong><small>{preparation.preflight.readiness.validatedChecks}/{preparation.preflight.readiness.totalChecks} 项服务端证据已验证，仍禁止 Provider submission。</small></span>
    </div> : null}
    {preparation.missingFields.length ? <div className="inline-alert inline-alert--warning" role="alert">
      <CircleAlert size={17} />
      <span><strong>尚未进入可执行准备态</strong><small>缺少：{preparation.missingFields.join('、')}</small></span>
    </div> : null}
    {input ? <details className="technical-details">
      <summary><span>不可变 director_fixed 输入摘要</span><ChevronRight size={16} /></summary>
      <div><pre style={{ margin: 0, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{JSON.stringify(input, null, 2)}</pre></div>
    </details> : null}
  </section>
}

export function ProductionComposer({ seed, directorFixedPreparation, onCreated, system, actorId, layout = 'standard' }: {
  seed: RemixSeed | null
  directorFixedPreparation?: DirectorFixedPreparation | null
  onCreated: (task: Task, open?: boolean) => void
  system: SystemStatus | null
  actorId: string | null
  layout?: 'standard' | 'studio'
}) {
  const directorFixed = Boolean(directorFixedPreparation)
  const composerRef = useRef<HTMLElement>(null)
  const feedbackId = useId()
  const paymentId = useId()
  /** 阻塞项列表的稳定 id：修好一条后 aria-describedby 指向的区域不会整体换掉。 */
  const blockerId = useId()
  const [storedSettings] = useState(() => loadVideoComposerSettings(
    typeof localStorage === 'undefined'
      ? { getItem: () => null }
      : localStorage,
  ))
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
  const [catalogLoading, setCatalogLoading] = useState(() => !directorFixed)
  const [catalogError, setCatalogError] = useState('')
  const [catalogReloadKey, setCatalogReloadKey] = useState(0)
  const [catalogReloadBusy, setCatalogReloadBusy] = useState(false)
  const [catalogLastAttempt, setCatalogLastAttempt] = useState('')
  const [elementCatalogError, setElementCatalogError] = useState('')
  const [elementsLoading, setElementsLoading] = useState(() => !directorFixed)
  const [elementCatalogReloadKey, setElementCatalogReloadKey] = useState(0)
  const [busy, setBusy] = useState(false)
  const [stage, setStage] = useState('正在上传素材')
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [submittedNotice, setSubmittedNotice] = useState('')
  const [uncertainSubmission, setUncertainSubmission] = useState<{
    clientTaskId: string
    idempotencyKey: string
    result: SubmissionRecoveryResult | null
    checking: boolean
  } | null>(null)
  const [resetting, setResetting] = useState(false)
  const [preview, setPreview] = useState<{ file: File; label: string } | null>(null)
  const storyboardInputRef = useRef<HTMLInputElement>(null)
  const batchInputRef = useRef<HTMLInputElement>(null)
  const resetTimerRef = useRef<number | null>(null)
  const uploadAbortRef = useRef<AbortController | null>(null)
  const submissionIdentityRef = useRef<{ clientTaskId: string; idempotencyKey: string } | null>(null)
  const submitLockRef = useRef(false)
  const dragDepthRef = useRef(0)
  const [dragOver, setDragOver] = useState(false)
  const [selectedMaterialId, setSelectedMaterialId] = useState<string | undefined>()
  const selectedMaterial = storyboards.find((item) => item.id === selectedMaterialId) ?? storyboards[0]
  const studio = layout === 'studio'
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
  const profileReady = generationMode === 'custom' || selectedProfile?.status === 'active'
  const templateAcceptsCount = Boolean(selectedTemplate && storyboards.length >= selectedTemplate.minImages && storyboards.length <= selectedTemplate.maxImages)
  const formLocked = busy || resetting || Boolean(uncertainSubmission)
  const batchMode = batchGroups.length > 0
  const invalidBatchGroup = batchGroups.find((group) => group.errors.length > 0
    || group.storyboards.length < (selectedTemplate?.minImages ?? 1)
    || group.storyboards.length > (selectedTemplate?.maxImages ?? storyboardLimit)
    || !getVideoDurationOptions(videoGeneration, group.storyboards.length).includes(normalizedDurationSeconds)
    || group.storyboards.length + Number(Boolean(group.productFront)) + Number(Boolean(group.productBack)) > referenceLimit)
  type CorrectionTarget = 'upload' | 'template' | 'subject' | 'prompt' | 'profile' | 'batch' | 'duration' | 'reload'
  type SubmissionBlocker = {
    /** 稳定 id：列表项与 aria-describedby 都引用它，修好一条后其余描述不会漂移。 */
    id: string
    message: string
    action?: string
    target?: CorrectionTarget
    /** 用户自己动手能解决 → 排前面；必须等管理员 → 排后面。 */
    selfService: boolean
  }
  // Submission and its recovery action share the same ordered validation.
  // 返回数组而不是「第一条」：维护模式解除后用户不会立刻撞上下一条被掩盖的阻塞（评审 I2）。
  const submissionBlockers = ((): SubmissionBlocker[] => {
    const blockers: SubmissionBlocker[] = []
    if (catalogLoading) return [{ id: 'catalog-loading', message: '正在读取生成配置，请稍候。', selfService: false }]
    if (catalogError) blockers.push({ id: 'catalog-error', message: catalogError.includes('当前处于维护模式') ? MAINTENANCE_MESSAGE : catalogError, action: '重新读取', target: 'reload', selfService: true })
    if (!selectedTemplate) return [...blockers, { id: 'no-template', message: '暂无可用视频模板，请联系管理员检查模板配置。', selfService: false }]
    // ↓ 以下分支都依赖 selectedTemplate，必须放在这个守卫之后，否则模板缺失时会读到 undefined。
    if (!providerAvailable) blockers.push({ id: 'provider-unavailable', message: `${activeProvider.displayLabel} 当前不可用。请让管理员配置凭据、启用通道并验证连接。`, selfService: false })
    if (selectedTemplate.status !== 'active') blockers.push({ id: 'template-unverified', message: '当前视频模板尚未通过生产验收。', action: '调整模板', target: 'template', selfService: true })
    if (invalidBatchGroup) {
      const group = invalidBatchGroup
      if (group.errors.length) blockers.push({ id: 'batch-errors', message: `${group.key}：${group.errors.join('、')}。请重新导入或退出批量编辑当前组。`, action: '检查批量素材', target: 'batch', selfService: true })
      else if (group.storyboards.length < selectedTemplate.minImages || group.storyboards.length > selectedTemplate.maxImages) blockers.push({ id: 'batch-count', message: `${group.key} 有 ${group.storyboards.length} 张分镜，当前模板接受 ${selectedTemplate.minImages}–${selectedTemplate.maxImages} 张。`, action: '调整模板', target: 'template', selfService: true })
      else if (!getVideoDurationOptions(videoGeneration, group.storyboards.length).includes(normalizedDurationSeconds)) blockers.push({ id: 'batch-duration', message: `${group.key} 当前支持 ${formatVideoDurationOptions(getVideoDurationOptions(videoGeneration, group.storyboards.length))}，不支持 ${normalizedDurationSeconds} 秒。`, action: '调整时长', target: 'duration', selfService: true })
      else blockers.push({ id: 'batch-references', message: `${group.key} 的分镜与主体图片总数超过模型的 ${referenceLimit} 张限制。请重新导入或退出批量编辑。`, action: '检查批量素材', target: 'batch', selfService: true })
      return blockers
    }
    if (!storyboards.length) blockers.push({ id: 'no-storyboard', message: '请至少上传 1 张分镜图', action: '添加素材', target: 'upload', selfService: true })
    else if (!templateAcceptsCount) blockers.push({ id: 'storyboard-count', message: `当前模板接受 ${selectedTemplate.minImages}–${selectedTemplate.maxImages} 张分镜图`, action: '调整模板', target: 'template', selfService: true })
    if (!subjectReady) blockers.push({ id: 'subject', message: subjectMode === 'upload' ? subjectValidation.errors[0] : '请选择一个可用的历史主体，或清除主体后按默认方式生成。', action: '编辑主体', target: 'subject', selfService: true })
    if (!providerInputsSupported) blockers.push({ id: 'provider-inputs', message: `当前模型 ${activeModel} 最多接收 ${referenceLimit} 张图片；系统不会静默丢弃分镜。`, action: '调整素材', target: 'subject', selfService: true })
    if (!profileReady) blockers.push({ id: 'profile', message: '当前站点风格尚未通过生产验收。', action: '选择站点风格', target: 'profile', selfService: true })
    if (!customPromptReady) blockers.push({ id: 'prompt', message: '请输入自定义提示词，或切换到自动化生成。', action: '填写提示词', target: 'prompt', selfService: true })
    // Array#sort 是稳定的，因此组内仍然保持校验先后顺序。
    return blockers.sort((left, right) => Number(right.selfService) - Number(left.selfService))
  })()
  const correctInput = (target: CorrectionTarget) => {
    if (formLocked) return
    if (target === 'reload') {
      // 维护模式下 /video-templates 会瞬间返回 503，catalogLoading 只存在几十毫秒，
      // 用户看到的是「点了没反应」（评审 I4）。这里给一个最小可见时长 + 上次尝试时间。
      if (catalogReloadBusy) return
      setCatalogReloadBusy(true)
      setCatalogLoading(true)
      setCatalogReloadKey((key) => key + 1)
      window.setTimeout(() => {
        setCatalogReloadBusy(false)
        setCatalogLastAttempt(new Date().toLocaleTimeString('zh-CN', { hour12: false }))
      }, CATALOG_RELOAD_MIN_VISIBLE_MS)
      return
    }
    const selectors: Record<Exclude<CorrectionTarget, 'reload'>, string> = {
      upload: '.studio-upload-actions button, .upload-zone',
      template: '.studio-template-controls select',
      subject: '.subject-input-panel button',
      prompt: '.custom-prompt-field textarea',
      profile: '.generation-route--automatic select',
      batch: '.studio-batch-mode button',
      duration: '.composer-duration-field select',
    }
    if (target === 'subject') {
      const disclosure = composerRef.current?.querySelector<HTMLDetailsElement>('.studio-subject-disclosure')
      if (disclosure) disclosure.open = true
    }
    const subjectUploadControl = target === 'subject' && subjectMode === 'upload'
      ? composerRef.current?.querySelector<HTMLElement>('.subject-upload-tile input[aria-invalid="true"]:not(:disabled)')
        ?? composerRef.current?.querySelector<HTMLElement>('.subject-upload-tile.is-required input:not(:disabled)')
      : null
    const control = subjectUploadControl ?? composerRef.current?.querySelector<HTMLElement>(selectors[target])
    const scrollTarget = subjectUploadControl?.closest('.subject-upload-tile') ?? control
    scrollTarget?.scrollIntoView({ block: 'center' })
    control?.focus({ preventScroll: true })
  }
  useEffect(() => {
    if (directorFixed) {
      return
    }
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
  }, [catalogReloadKey, directorFixed])
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
    if (directorFixed) {
      return
    }
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
        // 官方与自定义两个请求常常返回同一句错误，去重避免出现「xxx；xxx」。
        const failures = [...new Set(results
          .filter((result): result is PromiseRejectedResult => result.status === 'rejected')
          .map((result) => result.reason instanceof ApiError ? result.reason.message : '主体列表加载失败'))]
        setElementCatalogError(failures.join('；'))
      })
      .finally(() => {
        if (!controller.signal.aborted) setElementsLoading(false)
      })
    return () => controller.abort()
  }, [actorId, directorFixed, system, elementCatalogReloadKey])
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
  const moveMaterial = (id: string, offset: number) => {
    if (formLocked || batchMode) return
    setStoryboards((items) => {
      const index = items.findIndex((item) => item.id === id)
      const target = index + offset
      if (index < 0 || target < 0 || target >= items.length) return items
      const next = [...items]
      const [item] = next.splice(index, 1)
      next.splice(target, 0, item)
      return next
    })
  }
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
    if (directorFixed) return
    if (submitLockRef.current || formLocked || submissionBlockers.length) return
    submitLockRef.current = true
    setBusy(true)
    setError('')
    setNotice('')
    setSubmittedNotice('')
    setUncertainSubmission(null)
    const uploadController = new AbortController()
    uploadAbortRef.current?.abort()
    uploadAbortRef.current = uploadController
    let uploadFailure: unknown
    let createdGroups = 0
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
          const uploaded = await uploadStoryboard(file, uploadController.signal, sourceImageOutputId)
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
          mapWithConcurrency(group.storyboards, UPLOAD_CONCURRENCY, (file) => uploadOne(file, '分镜与主体素材', storyboards.find((item) => item.file === file)?.sourceImageOutputId)),
          validBatchGroups.length
            ? mapWithConcurrency([group.productFront, group.productBack].filter((file): file is File => Boolean(file)), UPLOAD_CONCURRENCY, (file) => uploadOne(file, '分镜与主体素材'))
            : mapWithConcurrency(subjectReferences, UPLOAD_CONCURRENCY, (reference) => uploadOne(reference.file, '分镜与主体素材')),
        ])
        setStage(generationMode === 'custom' ? `正在校验第 ${groupIndex + 1}/${submissionGroups.length} 组` : `正在创建第 ${groupIndex + 1}/${submissionGroups.length} 组任务`)
        setProgress(Math.round(52 + ((groupIndex + 1) / submissionGroups.length) * 46))
        const submissionIdentity = { clientTaskId: createUuid(), idempotencyKey: createUuid() }
        submissionIdentityRef.current = submissionIdentity
        window.localStorage.setItem(`libtv:submission-intent:${actorId ?? 'anonymous'}:${submissionIdentity.clientTaskId}`, JSON.stringify({
          ...submissionIdentity,
          kind: 'video',
          createdAt: new Date().toISOString(),
          requestHash: `${group.key}:${templateId}:${siteProfileId}:${normalizedDurationSeconds}:${resultCount}`,
        }))
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
          submissionIdentity,
        )
        window.localStorage.removeItem(`libtv:submission-intent:${actorId ?? 'anonymous'}:${submissionIdentity.clientTaskId}`)
        submissionIdentityRef.current = null
        if (!firstTask) firstTask = task
        createdGroups += 1
        if (batchMode) {
          const remaining = submissionGroups.slice(groupIndex + 1)
          setBatchGroups(remaining)
          if (remaining[0]) {
            setStoryboards(remaining[0].storyboards.map((file) => ({ id: createUuid(), file })))
            setSubjectFiles({ frontalImage: remaining[0].productFront, backImage: remaining[0].productBack, detailImages: [] })
          }
        }
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
      const identity = submissionIdentityRef.current
      const uncertain = identity && (
        failure instanceof ApiError
          ? failure.code === 'REQUEST_TIMEOUT' || failure.code === 'WRITE_UNCERTAIN' || failure.status >= 500
          : true
      )
      if (uncertain && identity) {
        setUncertainSubmission({ ...identity, result: null, checking: false })
        setError('提交结果未知，可能已创建任务；请先安全核对，不要直接重新提交。')
      } else {
        setError(failure instanceof Error ? failure.message : '素材提交失败，请检查图片后重试')
      }
      if (createdGroups) setSubmittedNotice(`已创建 ${createdGroups} 组任务；已成功的组不会再次提交。请处理剩余素材。`)
    } finally {
      if (uploadAbortRef.current === uploadController) uploadAbortRef.current = null
      setBusy(false)
      setProgress(0)
      submitLockRef.current = false
    }
  }

  const checkUncertainSubmission = async () => {
    if (!uncertainSubmission) return
    setUncertainSubmission((current) => current ? { ...current, checking: true } : current)
    try {
      const result = await querySubmissionRecovery({
        kind: 'video',
        clientId: uncertainSubmission.clientTaskId,
        idempotencyKey: uncertainSubmission.idempotencyKey,
      })
      setUncertainSubmission((current) => current ? { ...current, result, checking: false } : current)
      setError(result.state === 'submitted'
        ? '已找到原提交，请打开任务记录继续处理。'
        : result.state === 'in_progress'
          ? '原提交仍在核对中，请稍后刷新任务记录。'
          : result.state === 'unknown'
            ? '仍无法安全判断结果，请联系运营处理；系统不会自动重试。'
            : '暂未找到本地提交记录，这不代表 Provider 未收到请求；请联系运营处理。')
    } catch (cause) {
      setUncertainSubmission((current) => current ? { ...current, checking: false } : current)
      setError(cause instanceof Error ? cause.message : '安全核对失败，请稍后重试')
    }
  }

  const subjectPanel = <div className={studio ? 'studio-asset-panel' : 'composer-subject-panel'} inert={batchMode}>
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
      onReloadElements={() => { setElementsLoading(true); setElementCatalogReloadKey((current) => current + 1) }}
    />
  </div>

  if (directorFixedPreparation) return <DirectorFixedPreparationPanel preparation={directorFixedPreparation} />

  const handleModeKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (formLocked || !(event.target instanceof HTMLElement) || event.target.getAttribute('role') !== 'radio') return
    if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key)) return
    event.preventDefault()
    const next = event.key === 'Home' ? 'custom' : event.key === 'End' ? 'automatic' : generationMode === 'custom' ? 'automatic' : 'custom'
    setGenerationMode(next)
    event.currentTarget.querySelector<HTMLButtonElement>(`[data-mode="${next}"]`)?.focus()
  }
  const modeSelector = (mode: 'custom' | 'automatic') => <button
    type="button"
    className={`generation-route-selector${generationMode === mode ? ' is-selected' : ''}`}
    data-mode={mode}
    role="radio"
    tabIndex={generationMode === mode ? 0 : -1}
    aria-checked={generationMode === mode}
    disabled={formLocked}
    onClick={() => setGenerationMode(mode)}
  >
    <span className="generation-route-radio">{generationMode === mode ? <Check size={14} /> : null}</span>
    <span><strong>{mode === 'custom' ? '自定义提示词' : '自动化生成'}</strong></span>
  </button>
  const batchImportButton = <button type="button" className="text-button upload-batch-button" aria-label="按命名批量导入产品图与分镜" title="按命名批量导入产品图与分镜" disabled={formLocked} onClick={() => batchInputRef.current?.click()}><Images size={16} />{studio ? '批量导入' : '按命名批量导入产品图与分镜'}</button>

  return <section ref={composerRef} className={`composer${studio ? ' composer--studio' : ''}${busy ? ' is-busy' : ''}${resetting ? ' is-resetting' : ''}`} aria-label="视频制作配置" aria-busy={busy}>
    {uncertainSubmission ? <div className="inline-alert inline-alert--warning" role="alert">
      <CircleAlert size={17} />
      <span>
        <strong>提交结果未知</strong>
        <small>原始提交身份已保留。不要更换幂等键或直接重新生成。</small>
        {uncertainSubmission.result ? <small>核对结果：{uncertainSubmission.result.state}</small> : null}
      </span>
      <button type="button" className="secondary-button" disabled={uncertainSubmission.checking} onClick={() => void checkUncertainSubmission()}>
        {uncertainSubmission.checking ? <LoaderCircle className="spin" size={15} /> : <CheckCircle2 size={15} />}
        安全核对
      </button>
    </div> : null}
    <div className="composer-workspace">
    <div className="composer-inputs" inert={formLocked}>
      <div className="upload-panels upload-panels--with-subject">
        <div className="composer-asset-lane">
        <section className={`upload-panel upload-panel--storyboard${storyboards.length ? ' upload-panel--has-items' : ''}${dragOver ? ' is-drop-target' : ''}`} onDragEnter={() => {
          if (formLocked || batchMode) return
          dragDepthRef.current += 1
          setDragOver(true)
        }} onDragLeave={() => {
          dragDepthRef.current = Math.max(0, dragDepthRef.current - 1)
          if (!dragDepthRef.current) setDragOver(false)
        }} onDropCapture={() => { dragDepthRef.current = 0; setDragOver(false) }} onDragEnd={() => { dragDepthRef.current = 0; setDragOver(false) }} onDragOver={(event) => {
          if (formLocked || batchMode) return
          event.preventDefault()
          event.dataTransfer.dropEffect = event.dataTransfer.types.includes(MATERIAL_DRAG_TYPE) ? 'move' : 'copy'
        }} onDrop={(event) => { if (!formLocked && !batchMode) handleDrop(event, storyboards.length) }}>
          <input ref={storyboardInputRef} hidden type="file" multiple disabled={formLocked || batchMode} accept={IMAGE_FILE_ACCEPT} onChange={(event) => { addFiles(Array.from(event.target.files ?? [])); event.currentTarget.value = '' }} />
          <input ref={batchInputRef} hidden type="file" multiple disabled={formLocked} accept={IMAGE_FILE_ACCEPT} onChange={(event) => { addBatchFiles(Array.from(event.target.files ?? [])); event.currentTarget.value = '' }} />
          <div className="upload-panel-head"><div><h2>{studio ? '分镜素材' : '有序分镜'}</h2><small>至少 1 张，最多 {storyboardLimit} 张</small></div><span>{storyboards.length}/{storyboardLimit}</span>{studio ? batchImportButton : null}</div>
          <div className={studio ? 'studio-upload-actions' : undefined}>
          {studio ? <ImageUploadTrigger title={storyboards.length ? '继续添加分镜图' : '上传分镜图'} disabled={formLocked || batchMode} onClick={() => storyboardInputRef.current?.click()} /> : <button type="button" className="upload-zone upload-zone--compact" disabled={formLocked || batchMode} onClick={() => storyboardInputRef.current?.click()}><span className="upload-icon"><UploadCloud size={22} aria-hidden="true" /></span><span><strong>{storyboards.length ? '继续添加分镜图' : '上传分镜图'}</strong><small>JPG、PNG、WEBP</small></span></button>}
          {!studio ? batchImportButton : null}
          </div>
          {studio ? <Storyboard materials={storyboards} selectedId={selectedMaterial?.id} disabled={formLocked || batchMode} onSelect={setSelectedMaterialId} onMove={moveMaterial} onRemove={remove} onDropAt={handleDrop} onPreview={(material, index) => setPreview({ file: material.file, label: `分镜图 ${index + 1}` })} /> : null}
          {batchGroups.length ? <div className="batch-groups" aria-live="polite"><strong>批量识别</strong>{batchGroups.map((group) => <div key={group.key}><span>{group.key}</span><small>{group.productFront ? '正面已识别' : '缺正面'} · {group.productBack ? '背面已识别' : '无背面'} · {group.storyboards.length} 张分镜{group.errors.length ? ` · ${group.errors.join('、')}` : ''}</small></div>)}</div> : null}
          {batchMode ? <div className="studio-batch-mode"><span>当前预览：{batchGroups[0]?.key} · 批量 {batchGroups.length} 组</span><Button variant="ghost" onClick={() => setBatchGroups([])}>退出批量，编辑当前组</Button></div> : null}
          {!studio && storyboards.length ? <div className="materials-grid" aria-label="分镜图排序列表" inert={batchMode}>{storyboards.map((material, index) => <MaterialCard key={material.id} material={material} bucket="storyboard" index={index} onRemove={() => remove(material.id)} onDropAt={(event, target) => handleDrop(event, target)} onPreview={() => { setSelectedMaterialId(material.id); setPreview({ file: material.file, label: `分镜图 ${index + 1}` }) }} />)}</div> : null}
        </section>
        {studio ? <SubjectDisclosure
          initiallyOpen={Boolean(seed?.subjectFiles?.frontalImage)}
          status={batchMode ? '批量参考随产品导入' : subjectMode === 'history'
            ? elements.find((element) => element.id === elementId)?.name ?? '待选择历史主体'
            : subjectMode === 'upload' ? `${subjectReferenceCount} 张参考图` : '未设置 · 可选'}
        >
          {subjectPanel}
        </SubjectDisclosure> : subjectPanel}
        </div>
        <div className="composer-production-lane">
        <section className="generation-workflow" aria-labelledby="generation-workflow-title">
          {studio ? <div className="generation-workflow-heading"><div><h2 id="generation-workflow-title">生成配置</h2></div><div className="generation-mode-switch" role="radiogroup" aria-label="生成方式" onKeyDown={handleModeKeyDown}>{modeSelector('custom')}{modeSelector('automatic')}</div></div> : null}
          <TemplateSelector templates={templates} value={templateId} onChange={setTemplateId} disabled={formLocked} loading={catalogLoading} compact={studio} />
          {!studio ? <div className="generation-workflow-heading"><div><h2 id="generation-workflow-title">创意配置</h2></div></div> : null}
          <div className="generation-routes" role={studio ? undefined : 'radiogroup'} aria-label={studio ? undefined : '生成方式'} onKeyDown={studio ? undefined : handleModeKeyDown}>
            <article className={`generation-route generation-route--custom${generationMode === 'custom' ? ' is-active' : ' is-inactive'}`}>
              {!studio ? modeSelector('custom') : null}
              <div className="generation-route-body">
                <CustomPromptField scope="video" label={<>视频提示词<small className="custom-prompt-field__model">当前模型 {activeModel}</small></>} value={customPrompt} disabled={formLocked || generationMode !== 'custom'} describedBy={submissionBlockers.some((blocker) => blocker.target === 'prompt') ? blockerId : undefined} onChange={setCustomPrompt} placeholder="输入画面动作、镜头和节奏要求" />
              </div>
            </article>

            <article className={`generation-route generation-route--automatic${generationMode === 'automatic' ? ' is-active' : ' is-inactive'}`}>
              {!studio ? modeSelector('automatic') : null}
              <div className="generation-route-body">
                <label className="catalog-field"><span>站点风格</span><select value={siteProfileId} disabled={formLocked || catalogLoading || generationMode !== 'automatic'} onChange={(event) => setSiteProfileId(event.target.value)}>{profiles.map((item) => <option key={item.id} value={item.id}>{item.name}{item.status === 'active' ? '' : ' · 待验收'}</option>)}</select><small>{studio
                  ? catalogError ? '不可用' : catalogLoading ? '正在加载配置' : selectedProfile?.tone ?? '暂无可用站点风格'
                  : selectedProfile?.tone ?? '正在加载站点风格'}</small></label>
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
      </div>
    <div className="composer-feedback" id={feedbackId} aria-live="polite">
      {error ? <div className="inline-alert inline-alert--danger" role="alert"><AlertTriangle size={17} /><span>{error}</span></div> : null}
      {!formLocked && submissionBlockers.length ? <div className="inline-alert composer-next-action" id={blockerId} role="status">
        <CircleAlert size={17} aria-hidden="true" />
        <div className="composer-next-action-body">
          <strong>{submissionBlockers.length > 1 ? `开始生成前还有 ${submissionBlockers.length} 项需要处理` : '开始生成前还有 1 项需要处理'}</strong>
          <ul className="composer-next-action-list">
            {submissionBlockers.slice(0, 3).map((blocker) => {
              const reloading = blocker.target === 'reload' && catalogReloadBusy
              return <li key={blocker.id} id={`${blockerId}-${blocker.id}`}>
                <span>{reloading
                  ? '正在重新读取生成配置…'
                  : `${blocker.message}${blocker.target === 'reload' && catalogLastAttempt ? `（上次尝试 ${catalogLastAttempt} 仍未通过）` : ''}`}</span>
                {blocker.target ? <Button variant="ghost" busy={reloading} icon={<ArrowRight size={15} aria-hidden="true" />} onClick={() => correctInput(blocker.target!)}>{reloading ? '读取中' : blocker.action}</Button> : null}
              </li>
            })}
          </ul>
          {submissionBlockers.length > 3 ? <small>另有 {submissionBlockers.length - 3} 项未满足；逐项处理后本提示会自动收敛。</small> : null}
        </div>
      </div> : null}
      {submittedNotice ? <div className="inline-alert inline-alert--success" role="status"><CheckCircle2 size={17} /><span>{submittedNotice}</span></div> : null}
      {notice ? <div className="inline-alert" role="status"><CircleAlert size={17} /><span>{notice}</span></div> : null}
    </div>
    <div className="composer-submit-row" aria-live="polite">
      <fieldset className="result-count-field composer-result-count" disabled={formLocked}><legend>每组结果数</legend><div className="segmented-control">{([1, 2, 3, 4] as const).map((count) => <label key={count} className={resultCount === count ? 'is-selected' : ''}><input type="radio" name="result-count" value={count} checked={resultCount === count} onChange={() => setResultCount(count)} /><span>{count}</span></label>)}</div></fieldset>
      <label className="composer-duration-field" htmlFor="video-duration"><span>视频时长 <small id="video-duration-options">{durationOptionsLabel}</small></span><span><select id="video-duration" aria-label="视频时长" value={normalizedDurationSeconds} disabled={formLocked} aria-describedby="video-duration-options" onChange={(event) => setDurationSeconds(Number(event.target.value))}>{durationOptions.map((duration) => <option key={duration} value={duration}>{duration}</option>)}</select><small>秒</small></span></label>
      {busy ? <span className="composer-submit-status"><LoaderCircle className="spin" size={14} /><span>{stage}</span><strong>{progress}%</strong></span>
        : <span className="composer-submit-summary" id={paymentId}><LockKeyhole size={14} /><span><strong>{studio ? '预计结果 · ' : ''}{batchMode ? batchGroups.length : 1} 组 · {resultCount * (batchMode ? batchGroups.length : 1)} 个结果</strong><small>点击“开始生成”即确认付费提交</small></span></span>}
      <Button variant="primary" className="primary-button primary-button--large" aria-busy={busy} aria-describedby={busy ? undefined : [error || notice || submittedNotice ? feedbackId : null, submissionBlockers.length ? blockerId : null, paymentId].filter(Boolean).join(' ')} disabled={formLocked || submissionBlockers.length > 0} onClick={() => void submit()}>{busy ? <><LoaderCircle className="spin" size={18} />正在准备素材</> : resetting ? <><CheckCircle2 size={18} />已提交</> : <><WandSparkles size={18} />开始生成<ArrowRight size={17} /></>}</Button>
      {busy ? <div className="composer-submit-progress progress-track" role="progressbar" aria-label={stage} aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}><span style={studio ? { transform: `scaleX(${progress / 100})` } : { width: `${progress}%` }} /></div> : null}
    </div>
    </div>
    {preview ? studio
      ? <SourceInspector file={preview.file} label={preview.label} onClose={() => setPreview(null)} />
      : <ImagePreview file={preview.file} label={preview.label} onClose={() => setPreview(null)} /> : null}
  </section>
}
