import type { CreativeBrief } from './contracts'
import { DirectorApiError, type DirectorTaskResponse } from './directorApi'
import type { DirectorDraft } from './directorModel'
import type { ProductionBridgePreparation, ProductionBridgeChecks } from './productionBridge'

export function selectDirectorBriefSummary(brief: CreativeBrief) {
  return [
    { label: '商品', value: brief.productName.trim() || '未命名' },
    { label: '品牌', value: brief.brandMode === 'brand' ? brief.brandName.trim() || '未填写品牌' : '通用风格' },
    ...(brief.material?.trim() ? [{ label: '材质', value: brief.material.trim() }] : []),
    ...(brief.videoType?.trim() ? [{ label: '视频类型', value: brief.videoType.trim() }] : []),
    { label: '创作目标', value: brief.objective.trim() || '未填写' },
    { label: '目标受众', value: brief.audience.trim() || '未填写' },
    { label: '保留要求', value: brief.notes.trim() || '未填写' },
  ]
}

export function selectDirectorDirectionCards(workflow: DirectorTaskResponse | null, draft: DirectorDraft) {
  const confirmedDirectionId = workflow?.snapshot.package
    ? workflow.snapshot.plan?.selected_direction ?? draft.selectedDirectionId
    : null
  return draft.directions.map((direction) => ({
    ...direction,
    selected: draft.selectedDirectionId === direction.id,
    confirmed: confirmedDirectionId === direction.id,
  }))
}

export function selectDirectorPackageEvidence(workflow: DirectorTaskResponse | null, shotId: 'FIRST_FRAME' | 'SHOT_01') {
  return shotId === 'FIRST_FRAME'
    ? workflow?.snapshot.package ?? null
    : workflow?.snapshot.storyboard?.packages?.SHOT_01 ?? null
}

const checkDescriptions: Record<keyof ProductionBridgeChecks, { label: string; requirement: string }> = {
  ownerValidated: { label: '归属权限', requirement: '服务端确认当前用户对项目、包和素材的权限。' },
  packageRevisionValidated: { label: '生产包版本', requirement: '服务端核对当前 package revision；旧版本不能沿用。' },
  lockHashValidated: { label: '锁定项哈希', requirement: '服务端核对锁定项与授权所绑定的 locks hash。' },
  sourceHashValidated: { label: '来源哈希', requirement: '服务端验证来源内容哈希；本地预览不构成验证证据。' },
  qualificationValidated: { label: '生产资格', requirement: 'OFFLINE_SYNTHETIC_ONLY 不具备生产资格；离线选择或审核不能替代。' },
  licenseValidated: { label: '素材许可', requirement: '服务端提供适用许可与保留策略的证据。' },
  budgetValidated: { label: '预算证据', requirement: '服务端确认预算；Fake 授权不是付费生产授权。' },
  authorizationValidated: { label: '生产授权', requirement: '服务端核对作用域、到期时间、镜头和包绑定，并等待人工批准。' },
  executionStateValidated: { label: '执行状态', requirement: '服务端复核最新执行证据；UNKNOWN / WRITE_UNCERTAIN 需对账，不能重投。' },
  materializedSourcesValidated: { label: '物化来源映射', requirement: '服务端提供 materialized source mapping；object key 不是 Provider URL。' },
}

const nextStepLabels: Record<ProductionBridgePreparation['nextSteps'][number], string> = {
  SERVER_VALIDATED_PACKAGE_REQUIRED: '服务端复核生产包及关联证据',
  MATERIALIZED_SOURCE_MAPPING_REQUIRED: '服务端提供物化来源映射和许可证据',
  HUMAN_PROVIDER_AUTHORIZATION_REQUIRED: '人工 Checkpoint 1 与独立生产授权',
}

export function selectDirectorBridgeExplanation(
  preparation: ProductionBridgePreparation | null,
  workflow: DirectorTaskResponse | null,
) {
  if (!preparation) return null
  return {
    checks: (Object.keys(checkDescriptions) as Array<keyof ProductionBridgeChecks>).map((key) => ({
      key,
      ...checkDescriptions[key],
      status: preparation.checks[key] ? '准备层已记录，提交前仍需复核' : '待服务端验证',
    })),
    blockingReasons: preparation.blockingReasons,
    nextSteps: preparation.nextSteps.map((code) => ({ code, label: nextStepLabels[code] ?? code })),
    executionWarning: workflow?.snapshot.stopped
      ? `任务已停止${workflow.snapshot.stop_reason ? `：${workflow.snapshot.stop_reason}` : ''}。停止状态不能由前端解除。`
      : ['UNKNOWN', 'WRITE_UNCERTAIN'].includes(workflow?.snapshot.execution_state ?? '')
        ? `执行证据为 ${workflow?.snapshot.execution_state}，需服务端对账；禁止自动重投。`
        : null,
  }
}

const failureExplanations: Record<string, string> = {
  STALE_VERSION: '任务版本已变化。刷新任务状态，再核对原操作；不会自动重试。',
  IDEMPOTENCY_CONFLICT: '命令身份冲突。保留原命令证据并交由服务端核查。',
  TASK_IDEMPOTENCY_CONFLICT: '任务身份冲突。先核查已有任务，不重复创建。',
  EXECUTION_UNKNOWN: '执行结果未知。需服务端对账，不能重新提交生成。',
  WRITE_UNCERTAIN: '写入结果未确认。需服务端对账，不能重新提交生成。',
  RECONCILIATION_REQUIRED: '需服务端对账；前端不能推断执行成功或重新提交。',
  AUTHORIZATION_SCOPE_INVALID: '授权作用域不匹配。核对包与镜头授权，不扩展已有权限。',
  AUTHORIZATION_EXPIRED: '授权已过期。先核对最新包，再由人工重新确认授权。',
  STALE_PACKAGE: '生产包版本已变化。刷新并核对当前包及其授权。',
  STALE_CANDIDATE_PACKAGE: '候选不属于当前包。刷新后核对候选与生产包的绑定。',
  ASSET_HASH_MISMATCH: '素材哈希不匹配。需服务端核查来源；本地预览不能替代验证。',
  ASSET_REVOKED: '来源已撤销。需服务端核查，不沿用该来源。',
  ASSET_NOT_MATERIALIZED: '来源尚未物化。需服务端提供有效来源映射。',
  TEXT_CONTRACT_REJECTED: '文本合同被拒绝。核对服务端错误与包证据，不重写服务端 Prompt。',
  OFFLINE_WORKFLOW_DISABLED: '离线工作流当前不可用。由管理员核查，不切换到真实 Provider。',
  PAID_MODE_NOT_ALLOWED: '当前范围禁止付费执行，不开放生产提交。',
}

export function explainDirectorFailure(cause: unknown, fallback: string): string {
  if (!(cause instanceof DirectorApiError)) return fallback
  const explanation = failureExplanations[cause.code]
    ?? '未识别的服务端错误。保留原始代码和消息，等待核查；不推断成功或自动重试。'
  return `${cause.message} [${cause.code}] ${explanation}`
}
