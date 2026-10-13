import type { CreativeProject, CreativeTaskRecoveryReference } from '../../creative-project/types'
import { readDirectorPlanningSnapshot } from './directorHandoff'
import {
  createDirectorDraft,
  defaultDirectorDirections,
  directionsFromAnalysis,
  type DirectorDraft,
} from './directorModel'
import type { DirectorProductResponse, DirectorTaskResponse } from './directorApi'

export type DirectorRecoveryInvalidReason =
  | 'TASK_NOT_FOUND'
  | 'OWNER_MISMATCH'
  | 'PRODUCT_VERSION_STALE'
  | 'PRODUCT_REFERENCE_EXPIRED'
  | 'RECOVERY_REFERENCE_INVALID'

export type DirectorRecoveryErrorKind = DirectorRecoveryInvalidReason | 'NETWORK_ERROR'

export interface DirectorRecoveryValidation {
  valid: boolean
  reason?: DirectorRecoveryInvalidReason
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object'
}

export function readDirectorTaskRecovery(
  project: CreativeProject,
): CreativeTaskRecoveryReference | null {
  const value = project.metadata?.directorRecovery
  if (!isRecord(value) || value.schemaVersion !== 1 || typeof value.creative_task_id !== 'string') return null
  const product = isRecord(value.product_reference) ? value.product_reference : {}
  const index = isRecord(value.planning_snapshot_index) ? value.planning_snapshot_index : {}
  if (typeof index.state_version !== 'number' || typeof index.saved_at !== 'string') return null
  return {
    schemaVersion: 1,
    creative_task_id: value.creative_task_id,
    product_reference: {
      ...(typeof product.product_id === 'string' ? { product_id: product.product_id } : {}),
      ...(typeof product.product_version_id === 'string' ? { product_version_id: product.product_version_id } : {}),
      ...(typeof product.source_sha256 === 'string' ? { source_sha256: product.source_sha256 } : {}),
    },
    planning_snapshot_index: {
      state_version: index.state_version,
      ...(typeof index.package_revision === 'number' ? { package_revision: index.package_revision } : {}),
      saved_at: index.saved_at,
    },
  }
}

export function createDirectorTaskRecovery(
  task: DirectorTaskResponse,
  fallbackProductId?: string,
  now = new Date(),
): CreativeTaskRecoveryReference {
  const product = task.snapshot.product_version
  const packageRevision = task.snapshot.package?.revision
  return {
    schemaVersion: 1,
    creative_task_id: task.id,
    product_reference: {
      ...(product?.product_id || fallbackProductId
        ? { product_id: product?.product_id ?? fallbackProductId }
        : {}),
      ...(product?.product_version_id ? { product_version_id: product.product_version_id } : {}),
      ...(task.snapshot.asset?.sha256 ? { source_sha256: task.snapshot.asset.sha256 } : {}),
    },
    planning_snapshot_index: {
      state_version: task.state_version,
      ...(packageRevision === undefined ? {} : { package_revision: packageRevision }),
      saved_at: now.toISOString(),
    },
  }
}

export function validateDirectorTaskRecovery(
  reference: CreativeTaskRecoveryReference,
  task: DirectorTaskResponse,
): DirectorRecoveryValidation {
  if (reference.creative_task_id !== task.id) return { valid: false, reason: 'RECOVERY_REFERENCE_INVALID' }
  const product = task.snapshot.product_version
  if (task.snapshot.asset?.revoked) return { valid: false, reason: 'PRODUCT_REFERENCE_EXPIRED' }
  if (reference.product_reference.product_id && product?.product_id
    && reference.product_reference.product_id !== product.product_id) {
    return { valid: false, reason: 'PRODUCT_VERSION_STALE' }
  }
  if (reference.product_reference.product_version_id
    && reference.product_reference.product_version_id !== product?.product_version_id) {
    return { valid: false, reason: 'PRODUCT_VERSION_STALE' }
  }
  if (reference.product_reference.source_sha256
    && reference.product_reference.source_sha256 !== task.snapshot.asset?.sha256) {
    return { valid: false, reason: 'PRODUCT_REFERENCE_EXPIRED' }
  }
  return { valid: true }
}

export function validateDirectorProductReference(
  reference: CreativeTaskRecoveryReference,
  product: DirectorProductResponse,
): DirectorRecoveryValidation {
  if (reference.product_reference.product_id && reference.product_reference.product_id !== product.id) {
    return { valid: false, reason: 'PRODUCT_VERSION_STALE' }
  }
  if (reference.product_reference.product_version_id
    && product.current_version_id !== reference.product_reference.product_version_id) {
    return { valid: false, reason: 'PRODUCT_VERSION_STALE' }
  }
  return { valid: true }
}

export function classifyDirectorRecoveryError(error: unknown): DirectorRecoveryErrorKind {
  const code = isRecord(error) && typeof error.code === 'string' ? error.code : ''
  if (code === 'OWNER_MISMATCH' || code === 'TASK_OWNER_MISMATCH' || code === 'FORBIDDEN') return 'OWNER_MISMATCH'
  if (code === 'TASK_NOT_FOUND' || (isRecord(error) && error.status === 404)) return 'TASK_NOT_FOUND'
  if (code === 'PRODUCT_VERSION_STALE' || code === 'PRODUCT_VERSION_NOT_FOUND' || code === 'PRODUCT_VERSION_BLOCKED') {
    return 'PRODUCT_VERSION_STALE'
  }
  if (code === 'ASSET_REVOKED' || code === 'ASSET_MISSING' || code === 'ASSET_HASH_MISMATCH') {
    return 'PRODUCT_REFERENCE_EXPIRED'
  }
  return 'NETWORK_ERROR'
}

export function draftFromPersistedDirectorProject(
  project: CreativeProject,
  recovery: CreativeTaskRecoveryReference | null,
): DirectorDraft {
  const draft = createDirectorDraft()
  const planning = readDirectorPlanningSnapshot(project)
  if (!planning) {
    return recovery?.product_reference.product_id
      ? {
          ...draft,
          intake: {
            ...draft.intake,
            productFrontName: '已恢复商品引用',
          },
        }
      : draft
  }
  const directions = planning.candidates.length
    ? directionsFromAnalysis(planning.candidates.map((candidate) => ({
        id: candidate.id,
        scene: candidate.scene,
        behavior: candidate.behavior,
      })))
    : defaultDirectorDirections
  return {
    phase: planning.productionPackage ? 'package' : directions.length ? 'directions' : 'intake',
    intake: {
      ...draft.intake,
      productName: planning.brief.productName,
      productFrontName: recovery?.product_reference.product_id ? '已恢复商品引用' : '',
      brandMode: planning.brief.brandMode,
      brandName: planning.brief.brandName,
      material: planning.brief.material ?? '',
      videoType: planning.brief.videoType ?? '',
      modelGender: planning.brief.modelGender,
      modelAgeRange: planning.brief.modelAgeRange,
      videoDurationSeconds: planning.brief.videoDurationSeconds,
      videoAspectRatio: planning.brief.videoAspectRatio,
      objective: planning.brief.objective,
      audience: planning.brief.audience,
      notes: planning.brief.notes,
    },
    directions,
    selectedDirectionId: planning.selectedDirectionId,
  }
}

export function directorRecoveryMessage(kind: DirectorRecoveryErrorKind): string {
  switch (kind) {
    case 'TASK_NOT_FOUND':
      return '原导演任务已不存在，本地引用已清理。可以重新上传商品正面开始新任务。'
    case 'OWNER_MISMATCH':
      return '原导演任务不属于当前登录主体，本地引用已清理。可以重新开始任务。'
    case 'PRODUCT_VERSION_STALE':
      return '原商品版本已变化或失效，本地引用已清理。请重新确认商品后开始任务。'
    case 'PRODUCT_REFERENCE_EXPIRED':
      return '原商品引用已失效，本地引用已清理。请重新上传或选择商品。'
    case 'RECOVERY_REFERENCE_INVALID':
      return '本地导演任务引用不完整，已清理。可以重新开始任务。'
    case 'NETWORK_ERROR':
      return '任务恢复暂时失败，本地引用仍保留。请点击刷新后重试。'
  }
}
