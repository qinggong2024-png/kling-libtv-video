import { SUBJECT_MAX_DETAIL_IMAGES } from './subjectFiles'
import type { SubjectReferenceFiles } from './subjectFiles'

const SUBJECT_PANEL_DROP_EXCLUDE_SELECTOR = [
  'button',
  'a[href]',
  'input',
  'select',
  'textarea',
  '[contenteditable="true"]',
  '.subject-upload-tile',
].join(', ')

export function fillSubjectDropSlots(
  uploadedFiles: SubjectReferenceFiles,
  chosen: readonly File[],
): { files: SubjectReferenceFiles; acceptedCount: number } {
  let nextIndex = 0
  let frontalImage = uploadedFiles.frontalImage
  let backImage = uploadedFiles.backImage

  if (!frontalImage && chosen[nextIndex]) frontalImage = chosen[nextIndex++]
  if (!backImage && chosen[nextIndex]) backImage = chosen[nextIndex++]

  const availableDetailSlots = Math.max(
    0,
    SUBJECT_MAX_DETAIL_IMAGES - uploadedFiles.detailImages.length,
  )
  const addedDetails = chosen.slice(nextIndex, nextIndex + availableDetailSlots)
  nextIndex += addedDetails.length

  return {
    files: {
      frontalImage,
      backImage,
      detailImages: [...uploadedFiles.detailImages, ...addedDetails],
    },
    acceptedCount: nextIndex,
  }
}

export function isSubjectPanelDropExcluded(target: EventTarget | null): boolean {
  const element = target as Element | null
  return typeof element?.closest === 'function'
    && Boolean(element.closest(SUBJECT_PANEL_DROP_EXCLUDE_SELECTOR))
}
