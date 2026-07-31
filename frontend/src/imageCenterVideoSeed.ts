import type { ImageGenerationTask } from './imageCenterModel'
import type { SubjectReferenceFiles } from './subjectFiles'

export interface ImageCenterVideoSeed {
  id: string
  storyboards: File[]
  products: File[]
  subjectFiles: SubjectReferenceFiles
}

export function createImageCenterVideoSeed(
  task: Pick<ImageGenerationTask, 'product'>,
  storyboards: File[],
  selectedSubject: File,
  id: string,
): ImageCenterVideoSeed {
  return {
    id,
    storyboards,
    products: [task.product.front, task.product.back].filter((file): file is File => Boolean(file)),
    subjectFiles: {
      frontalImage: selectedSubject,
      backImage: null,
      detailImages: [],
    },
  }
}
