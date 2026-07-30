export const SUBJECT_MIN_IMAGES = 1
export const SUBJECT_MAX_IMAGES = 4
export const SUBJECT_MAX_DETAIL_IMAGES = 2
export const SUBJECT_MAX_IMAGE_BYTES = 10 * 1024 * 1024
export const SUBJECT_MAX_TOTAL_IMAGE_BYTES = 40 * 1024 * 1024
export const KLING_MAX_REFERENCES = 7

export const SUBJECT_IMAGE_ACCEPT = '.jpg,.jpeg,.png,image/jpeg,image/png'

export type SubjectInputMode = 'none' | 'upload' | 'history'
export type SubjectImageAngle = 'FRONT' | 'BACK' | 'SIDE_OR_DETAIL'
export type SubjectProviderImageRole = 'frontal_image' | 'refer_image'

export interface SubjectReferenceFiles {
  frontalImage: File | null
  backImage: File | null
  detailImages: File[]
}

export interface SubjectImageCandidate {
  name: string
  size: number
  type: string
}

export interface SubjectReferenceFileCandidates {
  frontalImage: SubjectImageCandidate | null
  backImage: SubjectImageCandidate | null
  detailImages: SubjectImageCandidate[]
}

export interface SubjectFileValidation {
  isValid: boolean
  fileCount: number
  errors: string[]
  fieldErrors: {
    frontalImage?: string
    detailImages?: string
  }
}

export interface SubjectImageReference {
  businessRole: 'SUBJECT_REFERENCE'
  angle: SubjectImageAngle
  providerRole: SubjectProviderImageRole
  file: File
}

export interface ReferenceBudget {
  isValid: boolean
  used: number
  remaining: number
  limit: number
  storyboardCount: number
  subjectCount: number
  error: string
}

function selectedFiles(files: SubjectReferenceFileCandidates): SubjectImageCandidate[] {
  return [
    ...(files.frontalImage ? [files.frontalImage] : []),
    ...(files.backImage ? [files.backImage] : []),
    ...files.detailImages,
  ]
}

export function createEmptySubjectReferenceFiles(): SubjectReferenceFiles {
  return {
    frontalImage: null,
    backImage: null,
    detailImages: [],
  }
}

export function getSubjectFileCount(files: SubjectReferenceFileCandidates): number {
  return selectedFiles(files).length
}

export function validateSubjectReferenceFiles(files: SubjectReferenceFileCandidates): SubjectFileValidation {
  const chosenFiles = selectedFiles(files)
  const errors: string[] = []
  const fieldErrors: SubjectFileValidation['fieldErrors'] = {}

  if (!files.frontalImage) {
    fieldErrors.frontalImage = '请上传一张清晰的服装正面图。'
    errors.push(fieldErrors.frontalImage)
  }

  if (files.detailImages.length > SUBJECT_MAX_DETAIL_IMAGES) {
    fieldErrors.detailImages = `侧面/细节图最多上传 ${SUBJECT_MAX_DETAIL_IMAGES} 张。`
    errors.push(fieldErrors.detailImages)
  }

  if (chosenFiles.length < SUBJECT_MIN_IMAGES || chosenFiles.length > SUBJECT_MAX_IMAGES) {
    errors.push(`新主体需要 ${SUBJECT_MIN_IMAGES}–${SUBJECT_MAX_IMAGES} 张参考图，当前已选择 ${chosenFiles.length} 张。`)
  }

  const unsupported = chosenFiles.find((file) => !['image/jpeg', 'image/png'].includes(file.type.toLowerCase()))
  if (unsupported) {
    errors.push(`“${unsupported.name}”不是支持的 JPG 或 PNG 图片。`)
  }

  const oversized = chosenFiles.find((file) => file.size > SUBJECT_MAX_IMAGE_BYTES)
  if (oversized) {
    errors.push(`“${oversized.name}”超过 10 MB 单文件上限。`)
  }

  const totalBytes = chosenFiles.reduce((sum, file) => sum + file.size, 0)
  if (totalBytes > SUBJECT_MAX_TOTAL_IMAGE_BYTES) {
    errors.push('主体参考图总大小不能超过 40 MB。')
  }

  const seen = new Set<SubjectImageCandidate>()
  const duplicate = chosenFiles.find((file) => {
    if (seen.has(file)) return true
    seen.add(file)
    return false
  })
  if (duplicate) {
    errors.push(`“${duplicate.name}”已在其他主体图片位置使用。`)
  }

  return {
    isValid: errors.length === 0,
    fileCount: chosenFiles.length,
    errors,
    fieldErrors,
  }
}

export function buildSubjectImageReferences(files: SubjectReferenceFiles): SubjectImageReference[] {
  return [
    ...(files.frontalImage
      ? [{
          businessRole: 'SUBJECT_REFERENCE' as const,
          angle: 'FRONT' as const,
          providerRole: 'frontal_image' as const,
          file: files.frontalImage,
        }]
      : []),
    ...(files.backImage
      ? [{
          businessRole: 'SUBJECT_REFERENCE' as const,
          angle: 'BACK' as const,
          providerRole: 'refer_image' as const,
          file: files.backImage,
        }]
      : []),
    ...files.detailImages.map((file) => ({
      businessRole: 'SUBJECT_REFERENCE' as const,
      angle: 'SIDE_OR_DETAIL' as const,
      providerRole: 'refer_image' as const,
      file,
    })),
  ]
}

export function getSubjectReferenceCount(
  mode: SubjectInputMode,
  files: SubjectReferenceFileCandidates,
  selectedElementId: string,
): number {
  if (mode === 'upload') return getSubjectFileCount(files)
  if (mode === 'history' && selectedElementId.trim()) return 1
  return 0
}

export function validateReferenceBudget(
  storyboardCount: number,
  subjectCount: number,
  limit = KLING_MAX_REFERENCES,
): ReferenceBudget {
  if (![storyboardCount, subjectCount, limit].every(Number.isInteger)
    || storyboardCount < 0
    || subjectCount < 0
    || limit < 1) {
    return {
      isValid: false,
      used: 0,
      remaining: 0,
      limit,
      storyboardCount,
      subjectCount,
      error: '引用数量必须是有效的非负整数。',
    }
  }

  const used = storyboardCount + subjectCount
  const remaining = Math.max(0, limit - used)
  return {
    isValid: used <= limit,
    used,
    remaining,
    limit,
    storyboardCount,
    subjectCount,
    error: used > limit
      ? `分镜与主体合计 ${used} 个引用，超过可灵 ${limit} 个引用上限。`
      : '',
  }
}
