import type { CreativeProject } from '../../creative-project/types'
import type { Task } from '../../types'
import { readDirectorPlanningSnapshot } from '../director-studio/directorHandoff'
import { prepareDirectorFixedOffline, prepareProductionBridge } from '../director-studio/productionBridge'

export type CreativeUiStatus = 'Draft' | 'Planning' | 'Preflight' | 'Ready' | 'Running' | 'Review' | 'Approved' | 'Blocked'

export const creativeUiStatuses = {
  Draft: { label: '草稿', tone: 'neutral' },
  Planning: { label: '规划中', tone: 'active' },
  Preflight: { label: '待预检', tone: 'warning' },
  Ready: { label: '输入就绪', tone: 'neutral' },
  Running: { label: '进行中', tone: 'active' },
  Review: { label: '待审核', tone: 'warning' },
  Approved: { label: '已人工批准', tone: 'success' },
  Blocked: { label: '需处理', tone: 'danger' },
} as const

export function presentCreativeWorkspace(project: CreativeProject, tasks: readonly Task[] = []) {
  const planning = readDirectorPlanningSnapshot(project)
  const pkg = planning?.productionPackage
  const direction = planning?.candidates.find((candidate) => candidate.id === planning.selectedDirectionId)
  const bridge = planning?.handoff ? prepareProductionBridge(planning.handoff, 'IMAGE_FIRST_FRAME') : null
  const videoPreparation = prepareDirectorFixedOffline(project)
  // Account-wide tasks must never be presented as project progress.
  const linkedTask = tasks.find((task) => task.id === project.workflowContext?.activeTaskId)
  const status: CreativeUiStatus = linkedTask
    ? linkedTask.variants.some((variant) => variant.generationStatus === 'UNKNOWN') ? 'Blocked'
      : linkedTask.phase === 'AWAITING_FINAL_APPROVAL' ? 'Review'
        : linkedTask.variants.length > 0 && linkedTask.variants.every((variant) => variant.finalApprovalStatus === 'APPROVED') ? 'Approved'
          : ['GENERATING', 'QUEUED', 'DOWNLOADING', 'VALIDATING'].includes(linkedTask.phase) ? 'Running'
            : ['FAILED', 'ACTION_REQUIRED', 'WRITE_UNCERTAIN'].includes(linkedTask.phase) ? 'Blocked'
              : 'Planning'
    : pkg ? 'Preflight' : planning?.candidates.length ? 'Planning' : 'Draft'
  const steps = [
    { id: 'direction', label: '创意方向', detail: direction?.title ?? '待选择', evidenced: Boolean(direction), surface: 'director' as const },
    { id: 'package', label: '生产包', detail: pkg ? `版本 r${pkg.revision}` : '待整理', evidenced: Boolean(pkg), surface: 'director' as const },
    { id: 'image', label: '图片', detail: '查看输入与结果', evidenced: false, surface: 'image' as const },
    { id: 'video', label: '视频', detail: linkedTask ? '已关联视频任务' : '查看分镜与配置', evidenced: Boolean(linkedTask), surface: 'video' as const },
    { id: 'review', label: '审核', detail: status === 'Approved' ? '服务端人工批准' : '人工审核', evidenced: status === 'Approved', surface: 'review' as const },
  ]
  const nextAction = status === 'Blocked'
    ? { label: '查看任务问题', surface: 'review' as const, description: '先核对任务与未知结果，避免重复提交。' }
    : status === 'Review'
      ? { label: '进入审核', surface: 'review' as const, description: '查看成品与审核证据，完成当前人工决定。' }
      : videoPreparation?.input
        ? { label: '查看视频准备', surface: 'video' as const, description: '分镜已有只读映射；生产预检与真实提交仍未开放。' }
        : pkg
          ? { label: '查看生产包与预检', surface: 'director' as const, description: '核对锁定生产包，继续离线首帧与分镜审核。' }
          : direction
            ? { label: '继续整理生产包', surface: 'director' as const, description: '查看已选方向与服务端生产包。' }
            : { label: planning?.candidates.length ? '选择创意方向' : '开始导演规划', surface: 'director' as const, description: '从商品输入与 Creative Brief 开始。' }
  return { planning, pkg, bridge, direction, status, steps, nextAction, linkedTask }
}
