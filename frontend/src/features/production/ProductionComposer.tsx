// 本文件由 App.tsx 拆分生成（2026-09-28 前端架构拆分 v2）。
import { AlertTriangle, ArrowRight, Check, CheckCircle2, ChevronRight, CircleAlert, Images, LoaderCircle, LockKeyhole, Settings, UploadCloud, WandSparkles } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
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
import { type Material, type RemixSeed, type UploadBucket, UPLOAD_CONCURRENCY } from './productionTypes'
import { MATERIAL_DRAG_TYPE, MaterialCard } from './MaterialCard'
import { formatTime } from '../../domain/taskPresentation'
import { ImagePreview } from '../../shared/components/Media'
import { SourceInspector } from '../../shared/components/studio/SourceInspector'
import { Storyboard } from '../../shared/components/studio/Storyboard'
import { TemplateSelector } from '../../shared/components/studio/TemplateSelector'
import { Button } from '../../shared/components/ui/Button'
import './videoStudio.css'

export function ProductionComposer({ seed, onCreated, system, actorId, layout = 'standard' }: {
  seed: RemixSeed | null
  onCreated: (task: Task, open?: boolean) => void
  system: SystemStatus | null
  actorId: string | null
  layout?: 'standard' | 'studio'
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
  const [catalogReloadKey, setCatalogReloadKey] = useState(0)
  const [elementCatalogError, setElementCatalogError] = useState('')
  const [elementsLoading, setElementsLoading] = useState(true)
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
  const productionReady = selectedTemplate?.status === 'active'
    && (generationMode === 'custom' || selectedProfile?.status === 'active')
  const templateAcceptsCount = Boolean(selectedTemplate && storyboards.length >= selectedTemplate.minImages && storyboards.length <= selectedTemplate.maxImages)
  const formLocked = busy || resetting || Boolean(uncertainSubmission)
  const batchMode = batchGroups.length > 0
  const batchInvalid = batchMode && batchGroups.some((group) => group.errors.length > 0
    || group.storyboards.length < (selectedTemplate?.minImages ?? 1)
    || group.storyboards.length > (selectedTemplate?.maxImages ?? storyboardLimit)
    || !getVideoDurationOptions(videoGeneration, group.storyboards.length).includes(normalizedDurationSeconds)
    || group.storyboards.length + Number(Boolean(group.productFront)) + Number(Boolean(group.productBack)) > referenceLimit)
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
  }, [catalogReloadKey])
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
    if (submitLockRef.current || formLocked || batchInvalid || !storyboards.length || !providerAvailable || !subjectReady || !providerInputsSupported || !productionReady || !templateAcceptsCount || !customPromptReady) return
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

  return <section className={`composer${studio ? ' composer--studio' : ''}${busy ? ' is-busy' : ''}${resetting ? ' is-resetting' : ''}`} aria-label="视频制作配置" aria-busy={busy}>
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
        <section className={`upload-panel upload-panel--storyboard${storyboards.length ? ' upload-panel--has-items' : ''}`} onDragOver={(event) => {
          if (formLocked || batchMode) return
          event.preventDefault()
          event.dataTransfer.dropEffect = event.dataTransfer.types.includes(MATERIAL_DRAG_TYPE) ? 'move' : 'copy'
        }} onDrop={(event) => { if (!formLocked && !batchMode) handleDrop(event, storyboards.length) }}>
          <input ref={storyboardInputRef} hidden type="file" multiple disabled={formLocked || batchMode} accept={IMAGE_FILE_ACCEPT} onChange={(event) => { addFiles(Array.from(event.target.files ?? [])); event.currentTarget.value = '' }} />
          <input ref={batchInputRef} hidden type="file" multiple disabled={formLocked} accept={IMAGE_FILE_ACCEPT} onChange={(event) => { addBatchFiles(Array.from(event.target.files ?? [])); event.currentTarget.value = '' }} />
          <div className="upload-panel-head"><div><h2>{studio ? '分镜素材' : '有序分镜'}</h2><small>至少 1 张，最多 {storyboardLimit} 张</small></div><span>{storyboards.length}/{storyboardLimit}</span></div>
          <div className={studio ? 'studio-upload-actions' : undefined}>
          <button type="button" className="upload-zone upload-zone--compact" disabled={formLocked || batchMode} onClick={() => storyboardInputRef.current?.click()}><span className="upload-icon"><UploadCloud size={22} /></span><span><strong>{storyboards.length ? '继续添加分镜图' : '上传分镜图'}</strong><small>JPG、PNG、WEBP</small></span></button>
          <button type="button" className="text-button upload-batch-button" disabled={formLocked} onClick={() => batchInputRef.current?.click()}><Images size={16} />按命名批量导入产品图与分镜</button>
          </div>
          {studio ? <Storyboard materials={storyboards} selectedId={selectedMaterial?.id} disabled={formLocked || batchMode} onSelect={setSelectedMaterialId} onMove={moveMaterial} onRemove={remove} onDropAt={handleDrop} onPreview={(material, index) => setPreview({ file: material.file, label: `分镜图 ${index + 1}` })} /> : null}
          {batchGroups.length ? <div className="batch-groups" aria-live="polite"><strong>批量识别</strong>{batchGroups.map((group) => <div key={group.key}><span>{group.key}</span><small>{group.productFront ? '正面已识别' : '缺正面'} · {group.productBack ? '背面已识别' : '无背面'} · {group.storyboards.length} 张分镜{group.errors.length ? ` · ${group.errors.join('、')}` : ''}</small></div>)}</div> : null}
          {batchMode ? <div className="studio-batch-mode"><span>当前预览：{batchGroups[0]?.key} · 批量 {batchGroups.length} 组</span><Button variant="ghost" onClick={() => setBatchGroups([])}>退出批量，编辑当前组</Button></div> : null}
          {!studio && storyboards.length ? <div className="materials-grid" aria-label="分镜图排序列表" inert={batchMode}>{storyboards.map((material, index) => <MaterialCard key={material.id} material={material} bucket="storyboard" index={index} onRemove={() => remove(material.id)} onDropAt={(event, target) => handleDrop(event, target)} onPreview={() => { setSelectedMaterialId(material.id); setPreview({ file: material.file, label: `分镜图 ${index + 1}` }) }} />)}</div> : null}
        </section>
        <div className={studio ? 'studio-asset-panel' : 'composer-subject-panel'} inert={batchMode}>
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
        </div>
        </div>
        <div className="composer-production-lane">
        <section className="generation-workflow" aria-labelledby="generation-workflow-title">
          {studio ? <div className="generation-workflow-heading"><div><h2 id="generation-workflow-title">生成配置</h2></div></div> : null}
          <TemplateSelector templates={templates} value={templateId} onChange={setTemplateId} disabled={formLocked} loading={catalogLoading} compact={studio} />
          {!studio ? <div className="generation-workflow-heading"><div><h2 id="generation-workflow-title">创意配置</h2></div></div> : null}
          <div className="generation-routes" role="radiogroup" aria-label="生成方式">
            <article className={`generation-route generation-route--custom${generationMode === 'custom' ? ' is-active' : ' is-inactive'}`}>
              <button type="button" className="generation-route-selector" role="radio" aria-checked={generationMode === 'custom'} disabled={formLocked} onClick={() => setGenerationMode('custom')}>
                <span className="generation-route-radio">{generationMode === 'custom' ? <Check size={14} /> : null}</span><span><strong>自定义提示词</strong></span>
              </button>
              <div className="generation-route-body">
                <CustomPromptField scope="video" label={`${activeModel} 提示词`} value={customPrompt} disabled={formLocked || generationMode !== 'custom'} onChange={setCustomPrompt} placeholder="输入画面动作、镜头和节奏要求" />
              </div>
            </article>

            <article className={`generation-route generation-route--automatic${generationMode === 'automatic' ? ' is-active' : ' is-inactive'}`}>
              <button type="button" className="generation-route-selector" role="radio" aria-checked={generationMode === 'automatic'} disabled={formLocked} onClick={() => setGenerationMode('automatic')}>
                <span className="generation-route-radio">{generationMode === 'automatic' ? <Check size={14} /> : null}</span><span><strong>自动化生成</strong></span>
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
      </div>
    <div className="composer-submit-row" aria-live="polite">
      <fieldset className="result-count-field composer-result-count" disabled={formLocked}><legend>每组结果数</legend><div className="segmented-control">{([1, 2, 3, 4] as const).map((count) => <label key={count} className={resultCount === count ? 'is-selected' : ''}><input type="radio" name="result-count" value={count} checked={resultCount === count} onChange={() => setResultCount(count)} /><span>{count}</span></label>)}</div></fieldset>
      <label className="composer-duration-field" htmlFor="video-duration"><span>视频时长 <small id="video-duration-options">{durationOptionsLabel}</small></span><span><select id="video-duration" aria-label="视频时长" value={normalizedDurationSeconds} disabled={formLocked} aria-describedby="video-duration-options" onChange={(event) => setDurationSeconds(Number(event.target.value))}>{durationOptions.map((duration) => <option key={duration} value={duration}>{duration}</option>)}</select><small>秒</small></span></label>
      {busy ? <span className="composer-submit-status"><LoaderCircle className="spin" size={14} /><span>{stage}</span><strong>{progress}%</strong></span>
        : <span className="composer-submit-summary"><LockKeyhole size={14} /><span><strong>{batchMode ? batchGroups.length : 1} 组 · {resultCount * (batchMode ? batchGroups.length : 1)} 个结果</strong><small>点击“开始生成”即确认付费提交</small></span></span>}
      <Button variant="primary" className="primary-button primary-button--large" disabled={formLocked || batchInvalid || catalogLoading || !storyboards.length || !providerAvailable || !subjectReady || !providerInputsSupported || !productionReady || !templateAcceptsCount || !customPromptReady} onClick={() => void submit()}>{busy ? <><LoaderCircle className="spin" size={18} />正在准备素材</> : resetting ? <><CheckCircle2 size={18} />已提交</> : <><WandSparkles size={18} />开始生成<ArrowRight size={17} /></>}</Button>
      {busy ? <div className="composer-submit-progress progress-track"><span style={{ width: `${progress}%` }} /></div> : null}
    </div>
    <div className="composer-feedback" aria-live="polite">
      {error ? <div className="inline-alert inline-alert--danger" role="alert"><AlertTriangle size={17} /><span>{error}</span></div>
        : catalogError ? <div className="inline-alert inline-alert--danger" role="alert"><AlertTriangle size={16} /><span>{catalogError}</span><Button variant="ghost" disabled={catalogLoading} onClick={() => { setCatalogLoading(true); setCatalogReloadKey((key) => key + 1) }}>重新读取</Button></div>
          : !selectedTemplate && !catalogLoading ? <div className="inline-alert" role="alert"><CircleAlert size={17} /><span>暂无可用视频模板，请联系管理员检查模板配置。</span></div>
          : batchInvalid ? <div className="inline-alert inline-alert--danger" role="alert"><AlertTriangle size={16} />批量素材有缺失或超出模板/模型数量限制，请重新导入或退出批量编辑当前组。</div>
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
    </div>
    {preview ? studio
      ? <SourceInspector file={preview.file} label={preview.label} onClose={() => setPreview(null)} />
      : <ImagePreview file={preview.file} label={preview.label} onClose={() => setPreview(null)} /> : null}
  </section>
}
