import { SUBJECT_MAX_DETAIL_IMAGES } from './subjectFiles'
import type { SubjectReferenceFiles } from './subjectFiles'

export type SubjectDragSlot = {
  slot: 'frontalImage' | 'backImage' | 'detailImages'
  index?: number
}

function getSubjectSlotFile(files: SubjectReferenceFiles, source: SubjectDragSlot): File | null {
  if (source.slot === 'frontalImage') return files.frontalImage
  if (source.slot === 'backImage') return files.backImage
  return typeof source.index === 'number' ? files.detailImages[source.index] ?? null : null
}

export function swapSubjectReferenceFiles(
  files: SubjectReferenceFiles,
  source: SubjectDragSlot,
  target: SubjectDragSlot,
): SubjectReferenceFiles {
  const sourceFile = getSubjectSlotFile(files, source)
  if (!sourceFile || (source.slot === 'detailImages' && typeof source.index !== 'number')) return files

  if (source.slot === 'detailImages' && target.slot === 'detailImages') {
    const sourceIndex = source.index as number
    const targetIndex = typeof target.index === 'number' ? target.index : files.detailImages.length - 1
    if (sourceIndex === targetIndex || targetIndex < 0 || targetIndex >= files.detailImages.length) return files
    const detailImages = [...files.detailImages]
    detailImages[sourceIndex] = detailImages[targetIndex]
    detailImages[targetIndex] = sourceFile
    return { ...files, detailImages }
  }

  const next = { ...files, detailImages: [...files.detailImages] }
  if (source.slot === 'detailImages') {
    const sourceIndex = source.index as number
    const targetFile = target.slot === 'frontalImage' ? files.frontalImage : files.backImage
    if (target.slot === 'frontalImage') next.frontalImage = sourceFile
    else if (target.slot === 'backImage') next.backImage = sourceFile
    next.detailImages.splice(sourceIndex, 1)
    if (targetFile) next.detailImages.splice(Math.min(sourceIndex, next.detailImages.length), 0, targetFile)
    return next
  }

  if (target.slot === 'detailImages') {
    const targetIndex = typeof target.index === 'number' ? target.index : next.detailImages.length
    if (targetIndex < next.detailImages.length) {
      const targetFile = next.detailImages[targetIndex]
      if (source.slot === 'frontalImage') next.frontalImage = targetFile
      else next.backImage = targetFile
      next.detailImages[targetIndex] = sourceFile
    } else if (next.detailImages.length < SUBJECT_MAX_DETAIL_IMAGES) {
      if (source.slot === 'frontalImage') next.frontalImage = null
      else next.backImage = null
      next.detailImages.push(sourceFile)
    }
    return next
  }

  const targetFile = target.slot === 'frontalImage' ? files.frontalImage : files.backImage
  if (source.slot === 'frontalImage') next.frontalImage = targetFile
  else next.backImage = targetFile
  if (target.slot === 'frontalImage') next.frontalImage = sourceFile
  else next.backImage = sourceFile
  return next
}
