import type { TaskNotification } from '../../browserNotifications'
import type { ImageGenerationOutput, ImageGenerationTask } from '../../imageCenterModel'

export type VideoSubjectSource = 'generated' | 'product-front' | 'product-back'

export interface ImageCenterVideoHandoff {
  task: ImageGenerationTask
  outputs: ImageGenerationOutput[]
  subjectSource: VideoSubjectSource
}

export interface ImageCenterProps {
  active: boolean
  draftScope: string | null
  openTaskId: string | null
  onPrepareVideos: (handoffs: ImageCenterVideoHandoff[], onSubmitted: () => void) => void | Promise<void>
  onNotifications: (events: ImageCenterNotificationEvent[]) => void
  onActiveTasksChange: (active: boolean) => void
}

export interface ImageCenterNotificationEvent {
  taskId: string
  status: ImageGenerationTask['status']
  notification: TaskNotification
}
