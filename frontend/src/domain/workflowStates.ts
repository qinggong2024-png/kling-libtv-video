// 前端状态机语义层（2026-09-21 前端架构拆分 v1）。
//
// 唯一事实来源是后端契约 backend/contracts/state-machines.json，
// 本文件只负责把它翻译成 UI 语义。约束由 domain/workflowStates.test.ts 强制：
// 契约新增/改名 phase 而未在此登记时，测试会失败。
//
// ★ 命名与契约的差异（勿误读）：
//   SETTLED_PHASES 是「计时器可以停下」的 UI 概念，**不是**后端的 terminal。
//   契约里 parentTask.terminal 只有 CANCELLED，DELIVERABLE / ACTION_REQUIRED 属 restingStates，
//   聚合仍可能把它们移走（重跑或被驳回）。这里沿用原名 TERMINAL 会与契约冲突，故改名。
import type { StatusTone } from '../types'

// ---------------------------------------------------------------- phase 集合

/**
 * 在途、且不需要用户介入的 phase。
 *
 * 注意 DOWNLOADING / VALIDATING 按设计意图属在途，虽当前不可达（见下）仍保留在集合内：
 * 它们代表「生成完成后还要下载/校验」这一设计，若后端将来实现，轮询与计时逻辑无需改动。
 * 把它们摘掉反而会让未来的实现静默漏掉轮询。
 */
export const ACTIVE_PHASES = new Set(['DRAFT', 'ANALYZING', 'PREPARING', 'WAITING_FOR_SEAL', 'QUEUED', 'GENERATING', 'DOWNLOADING', 'VALIDATING'])
/** 已经有可展示结果（含待终审）。 */
export const RESULT_PHASES = new Set(['AWAITING_FINAL_APPROVAL', 'DELIVERABLE', 'PARTIALLY_DELIVERABLE'])
/** 已交付。 */
export const COMPLETED_PHASES = new Set(['DELIVERABLE'])
/** 计时器停止推进 —— UI 概念，详见文件头说明。 */
export const SETTLED_PHASES = new Set(['DELIVERABLE', 'PARTIALLY_DELIVERABLE', 'ACTION_REQUIRED', 'CANCELLED'])
/** 走失败分支的 phase。 */
export const FAILED_PHASES = new Set(['ACTION_REQUIRED'])

/**
 * 需要用户动手才能继续的 phase。
 *
 * 新增于 2026-09-21：拆分前 AWAITING_CONFIRMATION **不属于任何集合**，
 * 全文件靠 9 处 `task.phase === 'AWAITING_CONFIRMATION'` 硬编码兜着
 * （旧 App.tsx 的 1170/1172/1181/1660/1787/1845/1866/3649/3655 行）。
 * 这里显式登记，使「每个 phase 都有归属」成为可断言的不变量；
 * 迁移那 9 处调用点属于后续独立改动，不在本轮范围内。
 */
export const AWAITING_USER_INPUT_PHASES = new Set(['AWAITING_CONFIRMATION', 'AWAITING_FINAL_APPROVAL', 'ACTION_REQUIRED'])

/**
 * 契约明确标注为 design-intent-only 的 phase：backend/src 零引用，
 * aggregate_parent_phase 永不返回，仅为满足「一 enum 一 key」才保留 key。
 * 前端保留标签以免出现裸枚举，但不应把它们当作可达分支。
 */
export const CONTRACT_UNREACHABLE_PHASES = new Set(['DOWNLOADING', 'VALIDATING'])

/** 所有语义分组的并集，用于断言「无未归类 phase」。 */
export const CLASSIFIED_PHASES = new Set([
  ...ACTIVE_PHASES,
  ...RESULT_PHASES,
  ...COMPLETED_PHASES,
  ...SETTLED_PHASES,
  ...FAILED_PHASES,
  ...AWAITING_USER_INPUT_PHASES,
  ...CONTRACT_UNREACHABLE_PHASES,
])

// ---------------------------------------------------------------- 展示映射

type StatusMeta = { label: string; tone: StatusTone }

/** parentTask 的 phase（契约 transitions 的 14 个 key）。 */
export const TASK_PHASE_META: Record<string, StatusMeta> = {
  DRAFT: { label: '正在上传素材', tone: 'neutral' },
  ANALYZING: { label: '正在分析图片', tone: 'active' },
  AWAITING_CONFIRMATION: { label: '等待确认方案', tone: 'warning' },
  PREPARING: { label: '正在准备生成', tone: 'active' },
  WAITING_FOR_SEAL: { label: '正在锁定生成任务', tone: 'active' },
  QUEUED: { label: '等待生成', tone: 'active' },
  GENERATING: { label: '正在生成视频', tone: 'active' },
  DOWNLOADING: { label: '正在下载成品', tone: 'active' },
  VALIDATING: { label: '正在校验成品', tone: 'active' },
  AWAITING_FINAL_APPROVAL: { label: '待最终审核', tone: 'warning' },
  PARTIALLY_DELIVERABLE: { label: '部分完成', tone: 'warning' },
  DELIVERABLE: { label: '已完成', tone: 'success' },
  ACTION_REQUIRED: { label: '任务需要处理', tone: 'danger' },
  CANCELLED: { label: '已取消', tone: 'neutral' },
}

/**
 * generationAttempt / variant 级状态，与 parentTask.phase 是**不同实体**。
 * 拆分前它们和 phase 混在同一张表里（旧 App.tsx:264-286）。
 */
export const ATTEMPT_STATUS_META: Record<string, StatusMeta> = {
  SUCCEEDED: { label: '已完成', tone: 'success' },
  PARTIAL: { label: '部分完成', tone: 'warning' },
  RUNNING: { label: '正在生成视频', tone: 'active' },
  PENDING: { label: '等待生成', tone: 'neutral' },
  FAILED: { label: '生成失败', tone: 'danger' },
  UNKNOWN: { label: '状态待确认', tone: 'warning' },
  READY: { label: '可下载', tone: 'success' },
}

/** 二者合并的查表，保持拆分前 `statusMeta[value]` 的调用方式可用。 */
export const statusMeta: Record<string, StatusMeta> = { ...TASK_PHASE_META, ...ATTEMPT_STATUS_META }

// ---------------------------------------------------------------- 其它常量

export const ANALYSIS_FAILURE_CODES = new Set([
  'ANALYSIS_TIMEOUT',
  'ANALYSIS_CANCELLED',
  'ANALYSIS_PROVIDER_FAILED',
  'ANALYSIS_STALE_RECOVERED',
  'ANALYSIS_SCHEMA_INVALID',
])

export const analysisStageLabels: Record<string, string> = {
  QUEUED: '等待后台分析',
  PREPARING_IMAGES: '正在准备图片',
  PROVIDER_RUNNING: '大模型正在分析素材',
  VALIDATING: '正在校验视频方案',
}
