// 本文件由 App.tsx 拆分生成（2026-09-28 前端架构拆分 v2）。
// 代码为逐字搬运，未经逻辑改写。
import { type MotionActionSummary, type SiteStyleProfileSummary } from '../../types'

export type ContentLibraryScope = 'general' | 'brand' | 'subjects'
export type ContentLibraryKind = 'actions' | 'styles'
export type ActionCategoryFilter = MotionActionSummary['category'] | 'all'

export const ACTION_CATEGORY_LABELS: Record<MotionActionSummary['category'], string> = {
  outfit: '整体穿搭',
  detail: '图案与面料',
  back: '背面展示',
  interaction: '人镜交流',
  product: '商品交互',
}

export function styleStatus(profile: SiteStyleProfileSummary) {
  if (profile.status === 'draft') return { label: '研究草稿', warning: true }
  if (profile.status === 'retired') return { label: '已停用', warning: true }
  return {
    label: profile.libraryScope === 'brand' ? '站点已验证' : '规则已验证',
    warning: profile.evidenceLevel !== 'verified_site',
  }
}
