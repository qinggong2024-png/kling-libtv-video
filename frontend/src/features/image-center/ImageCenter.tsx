/**
 * Compatibility entry point for the pre-Milestone 3 ImageCenter module.
 *
 * Runtime ownership now lives in ImageStudio. Existing imports stay valid
 * while the rest of the application moves incrementally.
 */
export {
  ImageStudio as ImageCenter,
  BatchImageOutputReview,
  ImageOutputCompare,
  ImageOutputReview,
  OutputCard,
} from '../image-studio'

export type {
  ImageCenterNotificationEvent,
  ImageCenterProps,
  ImageCenterVideoHandoff,
  VideoSubjectSource,
} from '../image-studio'
