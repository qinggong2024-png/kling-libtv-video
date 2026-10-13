import type { DirectorDirection } from './directorModel'

export type SpatialEvidence = 'user_locked' | 'observed' | 'proposed' | 'unknown'
export type SpatialPlanStatus = 'planned_not_verified' | 'visually_checked' | 'failed' | 'unverified'
export type KeyVisualDecision = 'keep' | 'merge' | 'optional'
export type KeyVisualAssetStatus = 'not_created' | 'planned_only' | 'existing_asset' | 'generated'

export interface SpatialAnchor {
  id: string
  object: string
  zone: string
  evidence: SpatialEvidence
}

export interface SceneFloorPlan {
  sceneId: string
  layoutRevision: string
  roomLabel: string
  origin: string
  positiveX: string
  positiveY: string
  units: 'qualitative_zones' | 'approximate_meters' | 'measured_meters'
  evidence: SpatialEvidence
  boundaries: string[]
  anchors: SpatialAnchor[]
  walkableRoute: string
  lightWorldDirection: string
  status: SpatialPlanStatus
}

export interface CameraPosition {
  cameraId: string
  worldZone: string
  worldHeading: string
  height: string
  distance: string
  lens: string
  operator: string
  screenRelation: string
  axisSide: 'side_A' | 'side_B' | 'neutral'
  transition: 'static' | 'continuous_move' | 'cut_reposition'
}

export interface CameraBlocking {
  actionAxis: string
  worldEndpoints: string[]
  establishedScreenDirection: string
  crossing: 'none' | 'on_camera_visible_move' | 'neutral_reset' | 'motivated_new_axis' | 'unresolved'
  directionOfMovement: string
  cameraTransitionReason: string
  positions: CameraPosition[]
  status: SpatialPlanStatus
}

export interface ActorState {
  worldZone: string
  bodyOrientation: string
  supportPoints: string[]
  handOccupancy: string[]
  gazeWorldTarget: string
}

export interface ActorBlocking {
  shotId: string
  start: ActorState
  movementPath: string[]
  pathType: 'walk' | 'turn' | 'reach' | 'stationary' | 'sit_to_stand'
  contactTransition: string
  end: ActorState
  connectionToNext: 'continuous_action' | 'continuity_cut' | 'intentional_time_jump' | 'scene_change'
  status: SpatialPlanStatus
}

export interface KeyVisualFrame {
  keyId: string
  shotIds: string[]
  trigger: string
  sceneId: string
  cameraId: string
  framing: string
  subjectWorldState: string
  productVisibility: string
  inheritFrom: string
  reason: string
  decision: KeyVisualDecision
  imageAssetStatus: KeyVisualAssetStatus
}

export interface KeyVisualPlan {
  version: '1.13.7'
  videoDurationSeconds: number
  shotCount: number
  keyVisualCount: number
  plannedImageCount: number
  authorizedImageCount: number
  generatedImageCount: number
  authorizedImageScope: 'not_authorized' | string
  status: 'planned_not_rendered' | 'image_ready' | 'unverified'
  selectionStrategy: 'minimum_sufficient_visual_changes'
  frames: KeyVisualFrame[]
  shotMapping: Record<string, { startVisual: string; endVisual: string; videoMotion: string }>
  coverageGap: string | null
}

export interface DirectorSpatialPlan {
  schemaVersion: '1.13.7'
  directionId: DirectorDirection['id']
  status: SpatialPlanStatus
  sourceEvidence: SpatialEvidence
  sceneFloorPlan: SceneFloorPlan
  cameraBlocking: CameraBlocking
  actorBlocking: ActorBlocking[]
  keyVisualPlan: KeyVisualPlan
}

function planForDirection(direction: DirectorDirection): {
  scene: SceneFloorPlan
  cameras: CameraPosition[]
  actor: ActorBlocking[]
  frames: KeyVisualFrame[]
  shotMapping: KeyVisualPlan['shotMapping']
} {
  const isStreet = direction.id === 'A'
  const isInterior = direction.id === 'B'
  const sceneId = isStreet ? 'STREET_01' : isInterior ? 'ROOM_01' : 'LIFE_01'
  const roomLabel = isStreet ? '城市街角' : isInterior ? '明亮室内' : '生活化空间'
  const anchors = isStreet
    ? [
        { id: 'A1', object: '橱窗', zone: '左前方', evidence: 'proposed' as const },
        { id: 'A2', object: '路缘与店招', zone: '右后方', evidence: 'proposed' as const },
      ]
    : isInterior
      ? [
          { id: 'A1', object: '窗户', zone: '主体左侧', evidence: 'proposed' as const },
          { id: 'A2', object: '沙发或桌面', zone: '主体后方', evidence: 'proposed' as const },
        ]
      : [
          { id: 'A1', object: '门口或入口边界', zone: '画面前方', evidence: 'proposed' as const },
          { id: 'A2', object: '生活道具台面', zone: '画面右后方', evidence: 'proposed' as const },
        ]

  const scene: SceneFloorPlan = {
    sceneId,
    layoutRevision: 'r1',
    roomLabel,
    origin: '主要入口或空间前边界（提案）',
    positiveX: '从入口看向右侧',
    positiveY: '从入口向空间内部',
    units: 'qualitative_zones',
    evidence: 'proposed',
    boundaries: isStreet ? ['建筑立面', '路缘', '可通行人行道'] : ['地面', '墙面', '门窗边界'],
    anchors,
    walkableRoute: isStreet ? '橱窗前 → 开放人行道 → 店招或街角' : '起始位置 → 开放通道 → 道具或窗边',
    lightWorldDirection: isInterior ? '窗光从主体左侧进入，方向独立于 camera-left' : '环境主光来自街道开放侧，方向保持跨镜一致',
    status: 'planned_not_verified',
  }

  const cameras: CameraPosition[] = [
    {
      cameraId: 'C1',
      worldZone: isStreet ? '橱窗前开放通道' : '起始位置正前方',
      worldHeading: isStreet ? '朝向 A2 与主体' : '朝向主体与 A1',
      height: '胸口高度（估计）',
      distance: '中距离（估计）',
      lens: '手机主摄 1x；待确认',
      operator: '第三人称手持摄影者',
      screenRelation: '主体占画面右三分之一，保留 A1',
      axisSide: 'side_A',
      transition: 'static',
    },
    {
      cameraId: 'C2',
      worldZone: isStreet ? '主体侧前方开放位置' : '窗侧可达位置',
      worldHeading: '沿同一运动轴斜向观察主体',
      height: '胸口高度（估计）',
      distance: '中近距离（估计）',
      lens: '手机主摄 1x；待确认',
      operator: '同一摄影者，经 cut_reposition 到位',
      screenRelation: '主体与产品展示面更清晰，A1/A2 形成视差',
      axisSide: 'side_A',
      transition: 'cut_reposition',
    },
    {
      cameraId: 'C3',
      worldZone: '主体前方可达位置',
      worldHeading: '朝向商品展示面',
      height: '胸口高度（估计）',
      distance: '近距离（估计）',
      lens: '手机主摄 1x；待确认',
      operator: '同一摄影者',
      screenRelation: '产品重点区域进入中近景',
      axisSide: 'side_A',
      transition: 'cut_reposition',
    },
  ]

  const start: ActorState = {
    worldZone: isStreet ? 'A1 与 A2 之间' : 'A1 与 A2 之间',
    bodyOrientation: '三分之二朝向主要行动方向',
    supportPoints: ['双脚着地'],
    handOccupancy: ['一手自然下垂'],
    gazeWorldTarget: '镜头附近',
  }
  const walkEnd: ActorState = {
    worldZone: isStreet ? 'A2 外侧开放通道' : '靠近 A2 的开放位置',
    bodyOrientation: '朝向行动终点',
    supportPoints: ['双脚着地'],
    handOccupancy: ['保持自然摆臂'],
    gazeWorldTarget: '镜头或前进方向',
  }
  const actor: ActorBlocking[] = [
    {
      shotId: 'S01',
      start,
      movementPath: [start.worldZone],
      pathType: 'stationary',
      contactTransition: '保持双脚支撑；仅允许整理衣摆或轻微转头',
      end: start,
      connectionToNext: 'continuity_cut',
      status: 'planned_not_verified',
    },
    {
      shotId: 'S02',
      start,
      movementPath: [start.worldZone, '开放通道', walkEnd.worldZone],
      pathType: 'walk',
      contactTransition: '重心从起始脚位转移到步行；不冻结上一镜位置',
      end: walkEnd,
      connectionToNext: 'continuity_cut',
      status: 'planned_not_verified',
    },
    {
      shotId: 'S03',
      start: walkEnd,
      movementPath: [walkEnd.worldZone],
      pathType: 'reach',
      contactTransition: '双脚保持支撑；手部接触商品或衣料展示区域',
      end: { ...walkEnd, handOccupancy: ['一手接触产品展示区域'] },
      connectionToNext: 'continuity_cut',
      status: 'planned_not_verified',
    },
    {
      shotId: 'S04',
      start: { ...walkEnd, handOccupancy: ['自然下垂'] },
      movementPath: [walkEnd.worldZone, isStreet ? 'A2 外侧' : 'A1 旁开放位置'],
      pathType: 'turn',
      contactTransition: '从展示动作恢复自然支撑，转身时保持脚下可达',
      end: { ...walkEnd, bodyOrientation: '朝向新的构图方向' },
      connectionToNext: 'intentional_time_jump',
      status: 'planned_not_verified',
    },
  ]

  const frames: KeyVisualFrame[] = [
    {
      keyId: 'K01',
      shotIds: ['S01'],
      trigger: 'scene_establish',
      sceneId,
      cameraId: 'C1',
      framing: '全身或大半身建立镜头',
      subjectWorldState: `${start.worldZone} · ${start.supportPoints.join('、')}`,
      productVisibility: '正面轮廓与主要商品细节可见',
      inheritFrom: '当前商品真值；场景提案',
      reason: '建立空间锚点、人物比例和产品初始展示',
      decision: 'keep',
      imageAssetStatus: 'not_created',
    },
    {
      keyId: 'K02',
      shotIds: ['S02'],
      trigger: 'camera_reposition',
      sceneId,
      cameraId: 'C2',
      framing: '大腿以上中景',
      subjectWorldState: `${walkEnd.worldZone} · 行走结束后双脚支撑`,
      productVisibility: '衣身正面在斜角透视下保持可读',
      inheritFrom: 'K01 · 同一 scene_id 与世界光源',
      reason: '机位和遮挡改变，需要新的稳定构图依据',
      decision: 'keep',
      imageAssetStatus: 'not_created',
    },
    {
      keyId: 'K03',
      shotIds: ['S03'],
      trigger: 'product_detail',
      sceneId,
      cameraId: 'C3',
      framing: '胸口至商品展示面近景',
      subjectWorldState: `${walkEnd.worldZone} · 手部接触展示区域`,
      productVisibility: '印花、面料或版型重点清晰',
      inheritFrom: 'K02 · 继承人物身份与场景锚点',
      reason: '产品信息结构发生变化，需要独立可读的商品构图',
      decision: 'keep',
      imageAssetStatus: 'not_created',
    },
    {
      keyId: 'K04',
      shotIds: ['S04'],
      trigger: 'actor_new_zone',
      sceneId,
      cameraId: 'C2',
      framing: '中景',
      subjectWorldState: `${walkEnd.worldZone} → 新构图方向 · 转身后重新建立支撑`,
      productVisibility: '产品与生活情境共同可见',
      inheritFrom: 'K03 · 允许记录动作结束后的世界位置变化',
      reason: '人物空间状态与构图重组，不能只靠微动作 Prompt 承接',
      decision: 'optional',
      imageAssetStatus: 'not_created',
    },
  ]

  return {
    scene,
    cameras,
    actor,
    frames,
    shotMapping: {
      S01: { startVisual: 'K01', endVisual: 'K01', videoMotion: '轻微转头或整理衣摆' },
      S02: { startVisual: 'K02', endVisual: 'K02', videoMotion: '沿开放通道自然行走，保持世界光源方向' },
      S03: { startVisual: 'K03', endVisual: 'K03', videoMotion: '短暂接触商品展示区域后回到自然手势' },
      S04: { startVisual: 'K04', endVisual: 'K04', videoMotion: '完成有依据的转身或剪辑后重新建立构图' },
    },
  }
}

function buildKeyVisualPlan(
  frames: KeyVisualFrame[],
  shotMapping: KeyVisualPlan['shotMapping'],
): KeyVisualPlan {
  const activeFrames = frames.filter((frame) => frame.decision !== 'merge')
  const plannedFrames = frames.filter((frame) => frame.decision === 'keep')
  const generatedFrames = frames.filter((frame) => frame.imageAssetStatus === 'generated')
  return {
    version: '1.13.7',
    videoDurationSeconds: 12,
    shotCount: Object.keys(shotMapping).length,
    keyVisualCount: activeFrames.length,
    plannedImageCount: plannedFrames.filter((frame) => frame.imageAssetStatus !== 'existing_asset').length,
    authorizedImageCount: 0,
    generatedImageCount: generatedFrames.length,
    authorizedImageScope: 'not_authorized',
    status: generatedFrames.length ? 'image_ready' : 'planned_not_rendered',
    selectionStrategy: 'minimum_sufficient_visual_changes',
    frames,
    shotMapping,
    coverageGap: null,
  }
}

export function createDirectorSpatialPlan(direction: DirectorDirection): DirectorSpatialPlan {
  const planning = planForDirection(direction)
  return {
    schemaVersion: '1.13.7',
    directionId: direction.id,
    status: 'planned_not_verified',
    sourceEvidence: 'proposed',
    sceneFloorPlan: planning.scene,
    cameraBlocking: {
      actionAxis: '主体运动方向',
      worldEndpoints: ['起始位置', '行动终点'],
      establishedScreenDirection: '主体从画面右侧向左侧移动；由真实机位决定',
      crossing: 'none',
      directionOfMovement: '沿开放通道朝行动终点',
      cameraTransitionReason: '机位变化服务于空间锚点、产品可见性或人物动作',
      positions: planning.cameras,
      status: 'planned_not_verified',
    },
    actorBlocking: planning.actor,
    keyVisualPlan: buildKeyVisualPlan(planning.frames, planning.shotMapping),
  }
}

export function setKeyVisualDecision(
  plan: DirectorSpatialPlan,
  keyId: string,
  decision: KeyVisualDecision,
): DirectorSpatialPlan {
  const frames = plan.keyVisualPlan.frames.map((frame) => (
    frame.keyId === keyId ? { ...frame, decision } : frame
  ))
  return {
    ...plan,
    keyVisualPlan: buildKeyVisualPlan(frames, plan.keyVisualPlan.shotMapping),
  }
}
