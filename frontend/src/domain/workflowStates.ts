// 本文件由 App.tsx 拆分生成（2026-09-28 前端架构拆分 v2）。
// 代码为逐字搬运，未经逻辑改写。
import { type StatusTone } from '../types'

export const ACTIVE_PHASES = new Set(['DRAFT', 'ANALYZING', 'PREPARING', 'WAITING_FOR_SEAL', 'QUEUED', 'GENERATING', 'DOWNLOADING', 'VALIDATING'])
export const RESULT_PHASES = new Set(['AWAITING_FINAL_APPROVAL', 'DELIVERABLE', 'PARTIALLY_DELIVERABLE'])
export const COMPLETED_PHASES = new Set(['DELIVERABLE'])
export const SETTLED_PHASES = new Set(['DELIVERABLE', 'PARTIALLY_DELIVERABLE', 'ACTION_REQUIRED', 'CANCELLED'])

export const FAILED_PHASES = new Set(['ACTION_REQUIRED'])
export const AWAITING_USER_INPUT_PHASES = new Set(['AWAITING_CONFIRMATION', 'AWAITING_FINAL_APPROVAL', 'ACTION_REQUIRED'])
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

export const statusMeta: Record<string, { label: string; tone: StatusTone }> = {
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
  SUCCEEDED: { label: '已完成', tone: 'success' },
  PARTIAL: { label: '部分完成', tone: 'warning' },
  RUNNING: { label: '正在生成视频', tone: 'active' },
  PENDING: { label: '等待生成', tone: 'neutral' },
  FAILED: { label: '生成失败', tone: 'danger' },
  UNKNOWN: { label: '状态待确认', tone: 'warning' },
  READY: { label: '可下载', tone: 'success' },
}
