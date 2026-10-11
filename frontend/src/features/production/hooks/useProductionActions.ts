// 本文件由 App.tsx 拆分生成（2026-09-21 前端架构拆分 v1）。
// 逐字搬运 App() 中的生产动作编排：改单、加载更早记录、复刻素材、一键复用、
// 图片中心视频交接、播放、新建任务回填。API 调用与顺序完全不变。
import { useCallback, useRef, useState } from 'react'
import { ApiError, confirmTask, fetchAssetFile, getTask, getTaskPage, reuseTask } from '../../../api'
import { variantDisplayName } from '../../../domain/taskPresentation'
import { createImageCenterVideoSeed } from '../../../imageCenterVideoSeed'
import type { Task, Variant, VariantKind } from '../../../types'
import { createUuid } from '../../../uuid'
import type { ImageCenterVideoHandoff } from '../../image-studio'
import { imageCenterOutputFile } from '../productionTypes'
import type { RemixSeed } from '../productionTypes'

type Options = {
  detailId: string | null
  nextTaskCursor: string | null
  loadingMoreTasks: boolean
  setLoadingMoreTasks: (value: boolean) => void
  setNextTaskCursor: (value: string | null) => void
  setTasks: React.Dispatch<React.SetStateAction<Task[]>>
  refreshTasks: () => Promise<void>
  setError: (message: string) => void
  navigate: (nextView: 'images' | 'make' | 'records' | 'library' | 'admin' | 'settings', nextDetailId?: string | null) => void
}

export function useProductionActions({
  detailId,
  nextTaskCursor,
  loadingMoreTasks,
  setLoadingMoreTasks,
  setNextTaskCursor,
  setTasks,
  refreshTasks,
  setError,
  navigate,
}: Options) {
  const [video, setVideo] = useState<{ artifactId: string; title: string } | null>(null)
  const [seed, setSeed] = useState<RemixSeed | null>(null)
  const [imageComposerSeed, setImageComposerSeed] = useState<RemixSeed | null>(null)
  const [remixStage, setRemixStage] = useState<'materials' | 'reuse' | null>(null)
  const pendingImageVideoSeedsRef = useRef<RemixSeed[]>([])
  const pendingImageSelectionClearRef = useRef<(() => void) | null>(null)

  const taskChanged = useCallback(async () => {
    if (detailId) {
      try {
        const changed = await getTask(detailId)
        setTasks((current) => current.map((task) => task.id === changed.id ? changed : task))
        return
      } catch { /* 下面的轮询刷新是兜底。 */ }
    }
    await refreshTasks()
  }, [detailId, refreshTasks, setTasks])

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
  }, [loadingMoreTasks, nextTaskCursor, setError, setLoadingMoreTasks, setNextTaskCursor, setTasks])

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
        } catch { /* 全局任务轮询仍是兜底。 */ }
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
        return createImageCenterVideoSeed(task, storyboards, outputs.slice(0, 6).map((output) => output.id), selectedSubject, createUuid())
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
  }, [navigate, setTasks])

  const imageComposerCreated = useCallback((task: Task) => {
    setTasks((current) => [task, ...current.filter((item) => item.id !== task.id)])
    pendingImageSelectionClearRef.current?.()
    pendingImageSelectionClearRef.current = null
    const nextSeed = pendingImageVideoSeedsRef.current.shift() ?? null
    setImageComposerSeed(nextSeed)
  }, [setTasks])

  const closeImageComposer = () => {
    pendingImageVideoSeedsRef.current = []
    pendingImageSelectionClearRef.current = null
    setImageComposerSeed(null)
  }

  const feedbackChanged = useCallback((changed: Task) => {
    setTasks((current) => current.map((task) => task.id === changed.id ? changed : task))
  }, [setTasks])

  return {
    video, setVideo,
    seed, setSeed,
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
  }
}
