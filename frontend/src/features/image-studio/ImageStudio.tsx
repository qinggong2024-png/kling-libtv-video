import { AlertTriangle, CheckCircle2, LoaderCircle, WandSparkles, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

import { ApiError, createImageGenerationBatch, getImageGenerationBatch, querySubmissionRecovery } from '../../api'
import {
  MAX_IMAGE_CENTER_OUTFITS,
  buildImageGenerationBatchRequest, buildWaitingTasks, calculateImageTaskSummary, compactImageAssetSet,
  createImageCenterDraft, createImageCenterRegenerationDraft, createOutfit, getOrderedImageReferences, getOrderedSelectedTasks,
  normalizeImageGenerationModes, normalizeImageGenerationQuality, parseStoryboardPrompt, validateImageCenterDraft,
} from '../../imageCenterModel'
import type { ImageGenerationBatch, ImageGenerationBatchItem } from '../../types'
import type {
  ImageCenterDraft, ImageGenerationMode, ImageGenerationOutput, ImageGenerationTask, OutfitDraft,
} from '../../imageCenterModel'
import { loadImageCenterDraft, saveImageCenterDraft } from '../../imageCenterStore'
import { createUuid } from '../../uuid'
import { imageTaskNotificationForTransition } from '../../browserNotifications'
import { readStorage, writeStorage } from '../../safeStorage'
import { DirectorStudio } from '../director-studio/DirectorStudio'
import '../image-center/imageReview.css'
import { BatchStudio } from './BatchStudio'
import { ImageRecords } from './ImageRecords'
import { ImageStudioHeader } from './ImageStudioHeader'
import { ImageToImageStudio } from './ImageToImageStudio'
import { TextToImageStudio } from './TextToImageStudio'
import { useImageStudioNavigation } from './imageStudioNavigation'
import { BatchCreationView } from './BatchCreationView'
import { ReferenceImageUpload } from './shared/ReferenceImageUpload'
import { bindImageReferenceSequence } from './imageReferenceSequence'
import { AssetPreviewDialog, BatchImageOutputReview, ImageOutputCompare, ImageOutputReview, OutputPreview, SelectionWorkbench } from './ImageResultTools'
import './imageStudio.css'

export { BatchImageOutputReview, ImageOutputCompare, ImageOutputReview, OutputCard } from './ImageResultTools'

import type {
  ImageCenterNotificationEvent,
  ImageCenterProps,
} from './contracts'

export type {
  ImageCenterNotificationEvent,
  ImageCenterProps,
  ImageCenterVideoHandoff,
  VideoSubjectSource,
} from './contracts'

const TERMINAL_IMAGE_STATUSES = new Set(['completed', 'failed', 'write_uncertain'])
type GenerationAvailability = 'checking' | 'available' | 'unavailable'

function isGenerationUnavailableError(cause: unknown): boolean {
  return cause instanceof ApiError
    && (cause.code === 'MAINTENANCE_QUERY_ONLY' || cause.status === 503 || cause.status === 403)
}

function generationUnavailableMessage(cause: unknown): string {
  if (cause instanceof ApiError && cause.code === 'MAINTENANCE_QUERY_ONLY') return '当前处于维护模式，仅支持登录和查询已保存任务，生成暂不可用。'
  if (cause instanceof ApiError && cause.status === 403) return '当前账号暂无生图权限，生成任务暂不可用，请联系管理员。'
  return '当前无法使用生图服务，创建任务已暂停，请稍后再试或联系管理员。'
}

function localTaskStatus(status: ImageGenerationBatchItem['status']) {
  return status
}

function mergeBatchIntoTasks(tasks: ImageGenerationTask[], batch: ImageGenerationBatch): ImageGenerationTask[] {
  const items = new Map(batch.items.map((item) => [item.clientTaskId, item]))
  return tasks.map((task) => {
    if (task.batchId !== batch.id && !items.has(task.id)) return task
    const item = items.get(task.id)
    if (!item) return task
    return {
      ...task,
      batchId: batch.id,
      clientBatchId: batch.clientBatchId ?? task.clientBatchId ?? null,
      providerTaskId: item.providerTaskId,
      providerTaskIds: item.providerTaskIds ?? (item.providerTaskId ? [item.providerTaskId] : []),
      modelId: item.modelId || task.modelId,
      status: localTaskStatus(item.status),
      outputs: item.outputs.map((output) => ({
        ...output,
        file: null,
        url: output.downloadUrl || output.url,
      })),
      error: item.error?.message ?? '',
      errorCode: item.error?.code ?? null,
      retryable: item.error?.retryable ?? null,
      errorDetails: item.error?.details,
    }
  })
}

export function ImageStudio(props: ImageCenterProps) {
  return <ScopedImageCenter key={props.draftScope ?? 'anonymous'} {...props} />
}

function ScopedImageCenter({ active, initialMode, draftScope, openTaskId, onPrepareVideos, onNotifications, onActiveTasksChange }: ImageCenterProps) {
  const { view: imageView, navigate: navigateImageView } = useImageStudioNavigation()
  const [draft, setDraft] = useState<ImageCenterDraft>(() => createImageCenterDraft(createUuid(), createUuid()))
  const [activeOutfitId, setActiveOutfitId] = useState('')
  const [loaded, setLoaded] = useState(false)
  const [saveState, setSaveState] = useState<'saved' | 'saving' | 'error'>('saved')
  const [notice, setNotice] = useState('')
  const [preparingVideos, setPreparingVideos] = useState(false)
  const [selectionBarExpanded, setSelectionBarExpanded] = useState(false)
  const [previewOutputId, setPreviewOutputId] = useState<string | null>(null)
  const [previewSource, setPreviewSource] = useState<{ file: File; label: string } | null>(null)
  const [reviewOutputId, setReviewOutputId] = useState<string | null>(null)
  const [compareOpen, setCompareOpen] = useState(false)
  const [batchReviewOpen, setBatchReviewOpen] = useState(false)
  const [commandBarHost, setCommandBarHost] = useState<HTMLDivElement | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [generationAvailability, setGenerationAvailability] = useState<GenerationAvailability>('checking')
  const [generationAvailabilityReason, setGenerationAvailabilityReason] = useState('')
  const studioMode = initialMode === 'director' ? 'director' : 'custom'
  const textDraftKey = `image-studio.text-prompt.${draftScope ?? 'anonymous'}`
  const [textPrompt, setTextPrompt] = useState(() => readStorage('local', textDraftKey) ?? '')
  const [textSaved, setTextSaved] = useState(true)
  const submissionInFlight = useRef(false)
  const saveTimerRef = useRef<number | null>(null)
  const latestDraftRef = useRef(draft)
  const loadedRef = useRef(false)
  const previousTaskStatusesRef = useRef<Map<string, ImageGenerationTask['status']>>(new Map())
  const notificationBaselineReadyRef = useRef(false)

  useEffect(() => {
    latestDraftRef.current = draft
    loadedRef.current = loaded
  }, [draft, loaded])
  useEffect(() => () => {
    if (!loadedRef.current) return
    if (saveTimerRef.current !== null) window.clearTimeout(saveTimerRef.current)
    void saveImageCenterDraft(draftScope, latestDraftRef.current).catch(() => { /* The page is already unmounted. */ })
  }, [draftScope])

  useEffect(() => {
    let active = true
    void loadImageCenterDraft(draftScope).then((stored) => {
      if (!active || stored?.version !== 1) return
      const defaults = createImageCenterDraft(stored.id, stored.outfits[0]?.id ?? createUuid(), stored.updatedAt)
      setDraft({
        ...stored,
        model: compactImageAssetSet(stored.model),
        outfits: stored.outfits.map((outfit) => ({ ...outfit, ...compactImageAssetSet(outfit) })),
        config: {
          ...defaults.config,
          ...stored.config,
          modes: normalizeImageGenerationModes(stored.config.modes),
          quality: normalizeImageGenerationQuality(stored.config.quality),
          outputFormat: 'png',
        },
        tasks: stored.tasks.map((task) => ({
          ...task,
          status: (task.status as string) === 'waiting_api' ? 'failed' : task.status,
          batchId: task.batchId ?? null,
          clientBatchId: task.clientBatchId ?? null,
          providerTaskId: task.providerTaskId ?? null,
          providerTaskIds: task.providerTaskIds ?? (task.providerTaskId ? [task.providerTaskId] : []),
          modelId: task.modelId ?? (task.provider === 'gpt' ? 'openai/gpt-image-2/edit' : 'google/nano-banana-2/edit'),
          aspectRatio: task.aspectRatio ?? defaults.config.aspectRatio,
          resolution: task.resolution ?? defaults.config.resolution,
          quality: task.quality ?? defaults.config.quality,
          outputFormat: 'png',
          allowBackInference: task.allowBackInference ?? true,
          storyboardShots: task.storyboardShots ?? parseStoryboardPrompt(task.prompt.storyboard),
          error: (task.status as string) === 'waiting_api' ? '此任务创建于 API 接入前，请重新生成。' : task.error,
          errorCode: task.errorCode ?? ((task.status as string) === 'waiting_api' ? 'LEGACY_DRAFT_TASK' : null),
          retryable: task.retryable ?? true,
        })),
      })
    }).catch(() => { if (active) setSaveState('error') }).finally(() => { if (active) setLoaded(true) })
    return () => { active = false }
  }, [draftScope])
  useEffect(() => {
    if (!loaded) return
    if (saveTimerRef.current !== null) window.clearTimeout(saveTimerRef.current)
    saveTimerRef.current = window.setTimeout(() => { void saveImageCenterDraft(draftScope, draft).then(() => setSaveState('saved')).catch(() => setSaveState('error')) }, 450)
    return () => { if (saveTimerRef.current !== null) window.clearTimeout(saveTimerRef.current) }
  }, [draft, draftScope, loaded])
  useEffect(() => {
    const controller = new AbortController()
    let active = true
    void fetch('/api/v1/system/status', { credentials: 'same-origin', cache: 'no-store', signal: controller.signal }).then((response) => {
      if (!active) return
      const maintenance = response.headers.get('x-libtv-maintenance')?.toLowerCase()
      if (maintenance === 'query-only') {
        setGenerationAvailability('unavailable')
        setGenerationAvailabilityReason('当前处于维护模式，仅支持登录和查询已保存任务，生成服务暂未开放。')
      } else if (!response.ok) {
        setGenerationAvailability('unavailable')
        setGenerationAvailabilityReason('当前无法确认生图服务状态，创建任务已暂停，请稍后再试或联系管理员。')
      } else {
        setGenerationAvailability('available')
        setGenerationAvailabilityReason('')
      }
    }).catch(() => {
      if (!active) return
      setGenerationAvailability('unavailable')
      setGenerationAvailabilityReason('当前无法连接生图服务，创建任务已暂停，请稍后再试或联系管理员。')
    })
    return () => {
      active = false
      controller.abort()
    }
  }, [])

  const hasActiveTasks = draft.tasks.some((task) => !TERMINAL_IMAGE_STATUSES.has(task.status))
  useEffect(() => {
    onActiveTasksChange(loaded && hasActiveTasks)
  }, [hasActiveTasks, loaded, onActiveTasksChange])

  useEffect(() => {
    if (!loaded) return
    const nextStatuses = new Map(draft.tasks.map((task) => [task.id, task.status]))
    if (!notificationBaselineReadyRef.current) {
      previousTaskStatusesRef.current = nextStatuses
      notificationBaselineReadyRef.current = true
      return
    }
    const events = draft.tasks.flatMap((task): ImageCenterNotificationEvent[] => {
      const notification = imageTaskNotificationForTransition(previousTaskStatusesRef.current.get(task.id), task)
      return notification ? [{ taskId: task.id, status: task.status, notification }] : []
    })
    previousTaskStatusesRef.current = nextStatuses
    if (events.length) onNotifications(events)
  }, [draft.tasks, loaded, onNotifications])

  const pollingBatchIds = useMemo(() => Array.from(new Set(draft.tasks
    .filter((task) => task.batchId && !TERMINAL_IMAGE_STATUSES.has(task.status))
    .map((task) => task.batchId!))).join('|'), [draft.tasks])
  useEffect(() => {
    if (!pollingBatchIds) return
    const batchIds = pollingBatchIds.split('|')
    const controller = new AbortController()
    let polling = false
    const poll = async () => {
      if (polling) return
      polling = true
      try {
        const batches = await Promise.all(batchIds.map((batchId) => getImageGenerationBatch(batchId, controller.signal)))
        setDraft((current) => ({
          ...current,
          tasks: batches.reduce(mergeBatchIntoTasks, current.tasks),
          updatedAt: new Date().toISOString(),
        }))
      } catch (cause) {
        if (!controller.signal.aborted) setNotice(cause instanceof ApiError ? cause.message : '生图任务状态刷新失败，稍后将自动重试。')
      } finally { polling = false }
    }
    void poll()
    const timer = window.setInterval(() => void poll(), 2500)
    return () => { controller.abort(); window.clearInterval(timer) }
  }, [pollingBatchIds])

  const updateDraft = (updater: (current: ImageCenterDraft) => ImageCenterDraft) => {
    setSaveState('saving')
    setDraft((current) => ({ ...updater(current), updatedAt: new Date().toISOString() }))
  }
  useEffect(() => {
    if (!active || !openTaskId) return
    navigateImageView('records', true)
    const frame = window.requestAnimationFrame(() => {
      document.getElementById(`image-task-${openTaskId}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    })
    return () => window.cancelAnimationFrame(frame)
  }, [active, navigateImageView, openTaskId])
  const summary = useMemo(() => calculateImageTaskSummary(draft), [draft])
  const errors = useMemo(() => validateImageCenterDraft(draft), [draft])
  const generationBlocked = generationAvailability !== 'available'
  const generationStatusMessage = generationAvailability === 'checking'
    ? '正在检查生图服务状态，请稍候。'
    : generationAvailabilityReason
  const selectedIds = useMemo(() => new Set(draft.selectedOutputIds), [draft.selectedOutputIds])
  const previewOutput = previewOutputId
    ? draft.tasks.flatMap((task) => task.outputs).find((output) => output.id === previewOutputId) ?? null
    : null
  const selectedCompareOutputs = draft.selectedOutputIds.slice(0, 2).map((id) => (
    draft.tasks.flatMap((task) => task.outputs).find((output) => output.id === id)
  )).filter((output): output is ImageGenerationOutput => Boolean(output))
  const reviewOutput = reviewOutputId ? draft.tasks.flatMap((task) => task.outputs).find((output) => output.id === reviewOutputId) : null
  const pendingReviewOutputs = useMemo(
    () => draft.tasks.flatMap((task) => task.outputs).filter((output) => output.qualificationStatus === 'PENDING'),
    [draft.tasks],
  )
  const previewSourceImage = (file: File, label: string) => {
    setPreviewOutputId(null)
    setPreviewSource({ file, label })
  }
  useEffect(() => {
    if (!draft.selectedOutputIds.length) setSelectionBarExpanded(false)
  }, [draft.selectedOutputIds.length])
  const activeOutfit = draft.outfits.find((outfit) => outfit.id === activeOutfitId) ?? draft.outfits[0]
  const activeOutfitIndex = Math.max(0, draft.outfits.findIndex((outfit) => outfit.id === activeOutfit.id))
  const referenceFiles = getOrderedImageReferences(draft.model, activeOutfit).map(({ file }) => file)
  const referenceLimit = draft.config.provider === 'nanobanana' ? 4 : 6
  const simpleDraft = {
    ...draft,
    outfits: [activeOutfit],
    config: { ...draft.config, modes: ['fusion'] as ImageGenerationMode[] },
  }
  const simpleSummary = calculateImageTaskSummary(simpleDraft)
  const simpleErrors = referenceFiles.length < 2 || !draft.model.front || !activeOutfit.front
    ? ['请至少上传 2 张参考图片。']
    : referenceFiles.length > referenceLimit ? [`当前模型最多支持 ${referenceLimit} 张参考图，请减少图片或切换模型。`]
      : validateImageCenterDraft(simpleDraft).map(error => error === '请填写多图融合提示词。' ? '请填写提示词。' : error)
  const batchEditor = imageView === 'batch-create' || imageView === 'batch-products' || imageView === 'batch-storyboard'
  const errorTarget = errors[0]?.includes('上传') ? '#asset-composer-title' : '#generation-config-title'
  const updateOutfit = (changed: OutfitDraft) => updateDraft((current) => ({ ...current, outfits: current.outfits.map((item) => item.id === changed.id ? changed : item) }))
  const addOutfit = () => {
    if (draft.outfits.length >= MAX_IMAGE_CENTER_OUTFITS) return
    const id = createUuid()
    setActiveOutfitId(id)
    updateDraft((current) => ({ ...current, outfits: [...current.outfits, createOutfit(id, current.outfits.length + 1)] }))
  }
  const removeOutfit = (id: string) => {
    if (draft.outfits.length <= 1) return
    const removedIndex = draft.outfits.findIndex((outfit) => outfit.id === id)
    const nextActive = draft.outfits[removedIndex + 1] ?? draft.outfits[removedIndex - 1]
    if (activeOutfit.id === id) setActiveOutfitId(nextActive?.id ?? '')
    updateDraft((current) => ({ ...current, outfits: current.outfits.filter((item) => item.id !== id) }))
  }
  const updateConfig = (changes: Partial<ImageCenterDraft['config']>) => updateDraft((current) => ({ ...current, config: { ...current.config, ...changes } }))
  const selectMode = (mode: ImageGenerationMode) => updateConfig({ modes: [mode] })
  const submitTaskSet = async (tasks: ImageGenerationTask[], expectedGenerationCount: number) => {
    if (!tasks.length || submissionInFlight.current) return
    const clientBatchId = createUuid()
    const identifiedTasks = tasks.map((task) => ({ ...task, clientBatchId }))
    const { manifest, files } = buildImageGenerationBatchRequest({
      clientBatchId,
      name: draft.name,
      expectedGenerationCount,
      tasks: identifiedTasks,
    })

    submissionInFlight.current = true
    setSubmitting(true)
    navigateImageView('records')
    updateDraft((current) => ({ ...current, activeTab: 'results', tasks: [...identifiedTasks, ...current.tasks], selectedOutputIds: [] }))
    await new Promise((resolve) => window.setTimeout(resolve, 0))
    updateDraft((current) => ({ ...current, tasks: current.tasks.map((task) => identifiedTasks.some((item) => item.id === task.id) ? { ...task, status: 'submitting' } : task) }))
    try {
      const batch = await createImageGenerationBatch(manifest, files)
      updateDraft((current) => ({ ...current, tasks: mergeBatchIntoTasks(current.tasks.map((task) => identifiedTasks.some((item) => item.id === task.id) ? { ...task, batchId: batch.id, clientBatchId } : task), batch) }))
      setNotice(`批次已提交，正在处理 ${expectedGenerationCount} 张图片。`)
    } catch (cause) {
      const uncertain = !(cause instanceof ApiError) || cause.code === 'REQUEST_TIMEOUT' || cause.code === 'WRITE_UNCERTAIN'
      const message = cause instanceof ApiError ? cause.message : '提交结果未知，请勿重复提交；稍后由管理员核对远端记录。'
      if (isGenerationUnavailableError(cause)) {
        setGenerationAvailability('unavailable')
        setGenerationAvailabilityReason(generationUnavailableMessage(cause))
      }
      updateDraft((current) => ({ ...current, tasks: current.tasks.map((task) => identifiedTasks.some((item) => item.id === task.id) ? {
        ...task,
        clientBatchId,
        status: uncertain ? 'write_uncertain' : 'failed',
        error: message,
        errorCode: cause instanceof ApiError ? cause.code : 'WRITE_UNCERTAIN',
        retryable: uncertain ? false : cause instanceof ApiError ? cause.retryable : false,
        errorDetails: cause instanceof ApiError ? cause.details : null,
      } : task) }))
      setNotice(message)
    } finally { submissionInFlight.current = false; setSubmitting(false) }
  }
  const submit = (source: ImageCenterDraft = draft) => {
    if (submissionInFlight.current) return
    if (generationBlocked) {
      setNotice(generationStatusMessage)
      return
    }
    const sourceErrors = validateImageCenterDraft(source)
    if (sourceErrors.length) { setNotice(sourceErrors[0]); return }
    const tasks = buildWaitingTasks(source, createUuid)
    void submitTaskSet(tasks, calculateImageTaskSummary(source).totalImages)
  }
  const prepareRegeneration = (source: ImageGenerationTask) => {
    if (source.status === 'write_uncertain') {
      setNotice('该批次提交结果未知，请先执行安全查询或联系管理员；不能直接重新生成。')
      return
    }
    const outfitId = createUuid()
    setActiveOutfitId(outfitId)
    navigateImageView('batch-create')
    updateDraft((current) => createImageCenterRegenerationDraft(current, source, outfitId))
    setNotice(`已载入「${source.outfitName}」的素材与生成配置。`)
    window.requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: 'smooth' }))
  }
  const recoverUncertainTask = async (task: ImageGenerationTask) => {
    if (task.status !== 'write_uncertain') return
    if (!task.clientBatchId) {
      setNotice('该批次缺少安全查询身份，请联系管理员核对；请勿重新生成。')
      return
    }
    try {
      const recovery = await querySubmissionRecovery({
        kind: 'image',
        clientId: task.clientBatchId,
        idempotencyKey: task.clientBatchId,
      })
      if (recovery.state === 'submitted' && recovery.resourceId) {
        const batch = await getImageGenerationBatch(recovery.resourceId)
        updateDraft((current) => ({
          ...current,
          tasks: mergeBatchIntoTasks(current.tasks, batch),
          updatedAt: new Date().toISOString(),
        }))
        setNotice('已恢复服务端批次记录，正在继续读取原任务状态；未创建新任务。')
        return
      }
      if (recovery.state === 'in_progress') {
        setNotice('服务端仍在处理原提交，请稍后再次查询；未创建新任务。')
        return
      }
      setNotice(recovery.state === 'unknown'
        ? '服务端记录存在歧义，已标记为需要管理员核对；请勿重新生成。'
        : '暂未找到原批次记录，不能据此判断未扣费；请联系管理员核对。')
    } catch (cause) {
      setNotice(cause instanceof ApiError ? cause.message : '安全查询失败，请稍后重试；请勿重新生成。')
    }
  }
  const updateOutputQuality = (id: string, values: Partial<ImageGenerationOutput>) => {
    updateDraft((current) => ({
      ...current,
      tasks: current.tasks.map((task) => ({
        ...task,
        outputs: task.outputs.map((output) => output.id === id ? { ...output, ...values } : output),
      })),
    }))
  }
  const toggleOutput = (id: string) => {
    const owner = draft.tasks.find((task) => task.outputs.some((output) => output.id === id))
    const output = owner?.outputs.find((item) => item.id === id)
    if (!owner || !output) return
    const alreadySelected = selectedIds.has(id)
    const selectedFromOwner = owner?.outputs.filter((output) => selectedIds.has(output.id)).length ?? 0
    if (!alreadySelected && selectedFromOwner >= 6) { setNotice('每套视频最多选择 6 张分镜，另保留 1 个主体引用名额。'); return }
    updateDraft((current) => ({ ...current, selectedOutputIds: current.selectedOutputIds.includes(id) ? current.selectedOutputIds.filter((item) => item !== id) : [...current.selectedOutputIds, id] }))
  }
  const rejectOutput = (id: string) => setReviewOutputId(id)
  const placeOutput = (taskId: string, outputId: string, beforeOutputId?: string) => {
    const owner = draft.tasks.find((task) => task.id === taskId && task.outputs.some((output) => output.id === outputId))
    if (!owner) return
    const alreadySelected = selectedIds.has(outputId)
    const selectedFromOwner = owner.outputs.filter((output) => selectedIds.has(output.id)).length
    if (!alreadySelected && selectedFromOwner >= 6) { setNotice('每套视频最多选择 6 张分镜，另保留 1 个主体引用名额。'); return }
    updateDraft((current) => {
      const nextIds = current.selectedOutputIds.filter((id) => id !== outputId)
      const targetIndex = beforeOutputId ? nextIds.indexOf(beforeOutputId) : -1
      if (targetIndex >= 0) nextIds.splice(targetIndex, 0, outputId)
      else {
        const currentOwner = current.tasks.find((task) => task.id === taskId)
        const ownerIds = new Set(currentOwner?.outputs.map((output) => output.id) ?? [])
        let insertionIndex = nextIds.length
        for (let index = nextIds.length - 1; index >= 0; index -= 1) {
          if (ownerIds.has(nextIds[index])) { insertionIndex = index + 1; break }
        }
        nextIds.splice(insertionIndex, 0, outputId)
      }
      return { ...current, selectedOutputIds: nextIds }
    })
  }
  const prepareVideos = async () => {
    if (preparingVideos) return
    const selectedTasks = getOrderedSelectedTasks(draft.tasks, draft.selectedOutputIds)
    if (!selectedTasks.length) return
    if (selectedTasks.some(({ outputs }) => outputs.some((output) => output.qualificationStatus !== 'QUALIFIED'))) {
      setNotice('只有已完成人工审核并标记为合格的图片才能进入视频生成。')
      return
    }
    const preparedOutputIds = new Set(selectedTasks.flatMap(({ outputs }) => outputs.map((output) => output.id)))
    setPreparingVideos(true)
    try {
      await onPrepareVideos(
        selectedTasks.map(({ task, outputs }) => ({ task, outputs, subjectSource: 'product-front' })),
        () => updateDraft((current) => ({
          ...current,
          selectedOutputIds: current.selectedOutputIds.filter((id) => !preparedOutputIds.has(id)),
        })),
      )
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : '无法准备视频制作素材。')
    } finally { setPreparingVideos(false) }
  }
  if (!loaded) return <div className="image-center-loading" hidden={!active}><LoaderCircle className="spin" size={24} /><strong>正在恢复图片批次</strong></div>

  return <div className={`image-center page-view${studioMode === 'director' ? ' image-center--director' : ' image-studio-workspace'}`} hidden={!active}>
    {notice ? <div className={`image-center-notice${errors.includes(notice) ? ' is-danger' : ''}`} role="status"><AlertTriangle size={16} /><span>{notice}</span><button type="button" onClick={() => setNotice('')} aria-label="关闭提示"><X size={15} /></button></div> : null}

    {studioMode === 'director' ? <DirectorStudio /> : null}
    {studioMode === 'custom' ? <ImageStudioHeader view={imageView} taskCount={draft.tasks.length}
      onOpen={(next) => { if (next === 'batch-create') selectMode('fusion'); navigateImageView(next) }} /> : null}
    <div id="image-studio-panel" role={studioMode === 'custom' && imageView !== 'records' ? 'tabpanel' : undefined}
      aria-labelledby={studioMode === 'custom' && imageView !== 'records' ? `image-mode-${batchEditor ? 'batch-create' : imageView}` : undefined}>
    {studioMode === 'custom' && imageView === 'image-to-image' ? <ImageToImageStudio
      config={draft.config} onChangeConfig={updateConfig} busy={submitting} blocked={generationBlocked} saveState={saveState}
      reason={generationStatusMessage} error={simpleErrors[0]} count={simpleSummary.totalImages}
      onGenerate={() => submit(simpleDraft)}
      references={<ReferenceImageUpload files={referenceFiles} boundRoles={getOrderedImageReferences(draft.model, activeOutfit).map(({ role }) => role)} maxFiles={referenceLimit} onPreview={previewSourceImage}
        onChange={(files) => {
          const { model, product } = bindImageReferenceSequence(files)
          updateDraft((current) => ({
            ...current, model,
            outfits: current.outfits.map((outfit) => outfit.id === activeOutfit.id ? { ...outfit, ...product } : outfit),
          }))
        }} />}
    /> : null}
    {studioMode === 'custom' && imageView === 'text-to-image' ? <TextToImageStudio
      prompt={textPrompt} saved={textSaved}
      onChange={(prompt) => { setTextPrompt(prompt); setTextSaved(writeStorage('local', textDraftKey, prompt)) }}
    /> : null}
    {studioMode === 'custom' && batchEditor ? <BatchStudio
      view={imageView} saveState={saveState}
      onOpen={(next) => { if (next === 'batch-storyboard') selectMode('storyboard'); if (next === 'batch-create') selectMode('fusion'); navigateImageView(next) }}
    >{batchEditor ? <BatchCreationView assetsOnly={imageView === 'batch-products'} draft={draft} summary={summary} activeOutfit={activeOutfit} activeOutfitIndex={activeOutfitIndex} generationStatusMessage={generationStatusMessage} errors={errors} updateDraft={updateDraft} updateConfig={updateConfig} selectMode={selectMode} addOutfit={addOutfit} removeOutfit={removeOutfit} setActiveOutfitId={setActiveOutfitId} updateOutfit={updateOutfit} /> : null}</BatchStudio> : null}
    {studioMode === 'custom' && imageView === 'records' ? <ImageRecords tasks={draft.tasks} selectedIds={selectedIds}
      selectedCompareOutputs={selectedCompareOutputs} pendingReviewOutputs={pendingReviewOutputs}
      onBack={() => navigateImageView('image-to-image')} onCreate={() => navigateImageView('image-to-image')}
      onCompare={() => setCompareOpen(true)} onBatchReview={() => setBatchReviewOpen(true)}
      recoverUncertainTask={recoverUncertainTask} prepareRegeneration={prepareRegeneration} previewSourceImage={previewSourceImage}
      toggleOutput={toggleOutput} rejectOutput={rejectOutput} onPreviewOutput={(id) => { setPreviewSource(null); setPreviewOutputId(id) }}
    /> : null}
    </div>
    {active && studioMode === 'custom' && batchEditor && imageView !== 'batch-products' ? <div className="image-studio-command-host" ref={setCommandBarHost} /> : null}
    {active && studioMode === 'custom' && batchEditor && imageView !== 'batch-products' && commandBarHost ? createPortal(<div className="image-center-command-bar image-studio-command-bar">
      <div><strong>{summary.outfitCount}/{draft.outfits.length} 套已就绪</strong><span>预计生成 {summary.totalImages} 张图片</span></div>
      {errors.length ? <a href={errorTarget}><AlertTriangle size={15} />{errors[0]}</a> : generationBlocked ? <span id="image-generation-availability" title={generationStatusMessage}><AlertTriangle size={15} />{generationStatusMessage}</span> : <span id="image-generation-availability" className="is-ready"><CheckCircle2 size={15} />配置完整</span>}
      <button type="button" className="primary-button" disabled={submitting || generationBlocked} onClick={() => submit()} title={generationBlocked ? generationStatusMessage : undefined} aria-describedby="image-generation-availability">{submitting ? <LoaderCircle className="spin" size={17} /> : <WandSparkles size={17} />}{submitting ? '正在提交' : generationBlocked ? '生成暂不可用' : '创建生图任务'}</button>
    </div>, commandBarHost) : null}
    {active && studioMode === 'custom' && imageView === 'records' && selectedIds.size ? createPortal(<SelectionWorkbench
      tasks={draft.tasks}
      selectedOutputIds={draft.selectedOutputIds}
      expanded={selectionBarExpanded}
      preparing={preparingVideos}
      onExpandedChange={setSelectionBarExpanded}
      onClear={() => updateDraft((current) => ({ ...current, selectedOutputIds: [] }))}
      onRemove={(outputId) => updateDraft((current) => ({ ...current, selectedOutputIds: current.selectedOutputIds.filter((id) => id !== outputId) }))}
      onPlaceOutput={placeOutput}
      onGenerate={() => void prepareVideos()}
    />, document.body) : null}
    {active && reviewOutput ? <ImageOutputReview key={reviewOutput.id} output={reviewOutput} onClose={() => setReviewOutputId(null)} onSaved={(values) => {
      updateOutputQuality(reviewOutput.id, values)
      if (values.qualificationStatus === 'REJECTED') updateDraft((current) => ({ ...current, selectedOutputIds: current.selectedOutputIds.filter((id) => id !== reviewOutput.id) }))
    }} /> : null}
    {active && batchReviewOpen ? <BatchImageOutputReview
      outputs={pendingReviewOutputs}
      onClose={() => setBatchReviewOpen(false)}
      onSaved={(outputId, values) => {
        updateOutputQuality(outputId, values)
        if (values.qualificationStatus === 'REJECTED') updateDraft((current) => ({ ...current, selectedOutputIds: current.selectedOutputIds.filter((id) => id !== outputId) }))
      }}
    /> : null}
    {active && previewOutput ? <OutputPreview
      output={previewOutput}
      selected={selectedIds.has(previewOutput.id)}
      onToggle={() => toggleOutput(previewOutput.id)}
      onClose={() => setPreviewOutputId(null)}
    /> : null}
    {active && previewSource ? <AssetPreviewDialog
      file={previewSource.file}
      label={previewSource.label}
      onClose={() => setPreviewSource(null)}
    /> : null}
    {active && compareOpen ? <ImageOutputCompare outputs={selectedCompareOutputs} onClose={() => setCompareOpen(false)} /> : null}
  </div>
}
