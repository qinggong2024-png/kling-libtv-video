import type { DirectorCandidate, DirectorTaskResponse } from './directorApi'
import type { DirectionCandidate } from './contracts'

export function canReviewDirectorCandidate(
  workflow: DirectorTaskResponse,
  candidate: DirectorCandidate,
): boolean {
  return workflow.mode === 'OFFLINE_FAKE_ONLY'
    && workflow.status === 'IMAGE_REVIEW'
    && !workflow.snapshot.stopped
    && !['UNKNOWN', 'WRITE_UNCERTAIN'].includes(workflow.snapshot.execution_state ?? '')
    && candidate.synthetic
    && candidate.shot_id === 'FIRST_FRAME'
    && candidate.package_id === workflow.snapshot.package?.package_id
}

export function canReviewDirectorStoryboardCandidate(
  workflow: DirectorTaskResponse,
  candidate: DirectorCandidate,
): boolean {
  return workflow.mode === 'OFFLINE_FAKE_ONLY'
    && workflow.status === 'STORYBOARD_REVIEW'
    && !workflow.snapshot.stopped
    && !['UNKNOWN', 'WRITE_UNCERTAIN'].includes(workflow.snapshot.execution_state ?? '')
    && candidate.synthetic
    && candidate.shot_id === 'SHOT_01'
    && candidate.package_id === workflow.snapshot.storyboard?.packages?.SHOT_01?.package_id
}

export function canSelectDirectorCandidate(
  workflow: DirectorTaskResponse,
  candidate: DirectorCandidate,
): boolean {
  return canReviewDirectorCandidate(workflow, candidate) && candidate.qualified
}

export function canSelectDirectorStoryboardCandidate(
  workflow: DirectorTaskResponse,
  candidate: DirectorCandidate,
): boolean {
  return canReviewDirectorStoryboardCandidate(workflow, candidate) && candidate.qualified
}

export function hasSelectedFirstFrame(workflow: DirectorTaskResponse): boolean {
  const selection = workflow.snapshot.selection
  return Boolean(
    selection?.shot_id === 'FIRST_FRAME'
      && workflow.snapshot.candidates.some((candidate) => (
        candidate.candidate_id === selection.candidate_id
          && candidate.shot_id === 'FIRST_FRAME'
          && candidate.qualified
          && candidate.synthetic
          && candidate.package_id === workflow.snapshot.package?.package_id
          && selection.package_id === candidate.package_id
      )),
  )
}

export function canAuthorizeStoryboard(workflow: DirectorTaskResponse): boolean {
  return workflow.mode === 'OFFLINE_FAKE_ONLY'
    && workflow.status === 'IMAGE_REVIEW'
    && !workflow.snapshot.stopped
    && !['UNKNOWN', 'WRITE_UNCERTAIN'].includes(workflow.snapshot.execution_state ?? '')
    && hasSelectedFirstFrame(workflow)
    && Boolean(workflow.snapshot.package)
    && workflow.snapshot.authorization?.scope !== 'VIDEO_STORYBOARD'
}

export type DirectorBrandMode = 'brand' | 'generic'
export type DirectorPhase = 'intake' | 'directions' | 'package'

export interface DirectorProductIntake {
  productName: string
  productFrontName: string
  productFrontPreviewUrl: string
  productFrontFile?: File
  brandMode: DirectorBrandMode
  brandName: string
  material: string
  videoType: string
  modelGender?: string
  modelAgeRange?: string
  videoDurationSeconds?: number
  videoAspectRatio?: string
  objective: string
  audience: string
  notes: string
}

export type DirectorDirection = DirectionCandidate

export interface DirectorDraft {
  phase: DirectorPhase
  intake: DirectorProductIntake
  directions: DirectorDirection[]
  selectedDirectionId: DirectorDirection['id'] | null
}

export function directionsFromAnalysis(
  directions: Array<{ id: DirectorDirection['id']; scene: string; behavior: string }>,
): DirectorDirection[] {
  const defaults = new Map(defaultDirectorDirections.map((direction) => [direction.id, direction]))
  return directions.map((direction) => {
    const fallback = defaults.get(direction.id)
    if (!fallback) return defaultDirectorDirections[0]
    return {
      ...fallback,
      summary: `${direction.scene}，${direction.behavior}。`,
      scene: direction.scene,
      behavior: direction.behavior,
    }
  })
}

export const defaultDirectorDirections: DirectorDirection[] = [
  {
    id: 'A',
    title: '干净街拍',
    summary: '把商品细节放在自然行走和城市光线里。',
    human: '自然行走',
    scene: '城市街角',
    behavior: '回身看镜头',
    camera: '中近景跟拍',
    emotion: '轻松自信',
  },
  {
    id: 'B',
    title: '安静质感',
    summary: '用克制的室内光线突出面料、版型和轮廓。',
    human: '静态站姿',
    scene: '明亮室内',
    behavior: '整理衣摆',
    camera: '固定半身',
    emotion: '沉静专注',
  },
  {
    id: 'C',
    title: '生活动作',
    summary: '用一个可识别的生活动作建立穿着情境。',
    human: '自然互动',
    scene: '生活化空间',
    behavior: '拿取随身物品',
    camera: '广角推近',
    emotion: '轻快真实',
  },
]

export function createDirectorDraft(): DirectorDraft {
  return {
    phase: 'intake',
    intake: {
      productName: '',
      productFrontName: '',
      productFrontPreviewUrl: '',
      brandMode: 'generic',
      brandName: '',
      material: '',
      videoType: '',
      objective: '',
      audience: '',
      notes: '',
    },
    directions: defaultDirectorDirections,
    selectedDirectionId: null,
  }
}

export function isDirectorIntakeReady(intake: DirectorProductIntake): boolean {
  return Boolean(intake.productFrontName)
    && (intake.brandMode === 'generic' || Boolean(intake.brandName.trim()))
}

export function selectDirectorDirection(
  draft: DirectorDraft,
  directionId: DirectorDirection['id'],
): DirectorDraft {
  return {
    ...draft,
    phase: 'directions',
    selectedDirectionId: directionId,
  }
}
