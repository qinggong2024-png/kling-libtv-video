export type DirectorBrandMode = 'brand' | 'generic'
export type DirectorPhase = 'intake' | 'directions' | 'package'

export interface DirectorProductIntake {
  productName: string
  productFrontName: string
  productFrontPreviewUrl: string
  brandMode: DirectorBrandMode
  brandName: string
  notes: string
}

export interface DirectorDirection {
  id: 'A' | 'B' | 'C'
  title: string
  summary: string
  human: string
  scene: string
  behavior: string
  camera: string
  emotion: string
}

export interface DirectorDraft {
  phase: DirectorPhase
  intake: DirectorProductIntake
  directions: DirectorDirection[]
  selectedDirectionId: DirectorDirection['id'] | null
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
      notes: '',
    },
    directions: defaultDirectorDirections,
    selectedDirectionId: null,
  }
}

export function isDirectorIntakeReady(intake: DirectorProductIntake): boolean {
  return Boolean(intake.productFrontName)
}

export function selectDirectorDirection(
  draft: DirectorDraft,
  directionId: DirectorDirection['id'],
): DirectorDraft {
  return {
    ...draft,
    phase: 'package',
    selectedDirectionId: directionId,
  }
}
