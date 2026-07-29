import type { FeedbackReason, FeedbackValue } from './types'

type FeedbackOption = { value: FeedbackReason; label: string }

export const FEEDBACK_OPTIONS: Record<FeedbackValue, FeedbackOption[]> = {
  LIKE: [
    { value: 'GARMENT_ACCURATE', label: '服装还原好' },
    { value: 'PRODUCT_CLEAR', label: '商品展示清晰' },
    { value: 'NATURAL_MOTION', label: '动作自然' },
    { value: 'COMFORTABLE_CAMERA', label: '运镜舒服' },
    { value: 'GOOD_PACING', label: '节奏合适' },
    { value: 'STRONG_APPEAL', label: '有广告感' },
  ],
  DISLIKE: [
    { value: 'GARMENT_DISTORTED', label: '服装变形' },
    { value: 'COLOR_INACCURATE', label: '颜色不准' },
    { value: 'LOGO_TEXT_INCORRECT', label: 'Logo / 文字错误' },
    { value: 'FACE_HAND_ARTIFACT', label: '脸或手异常' },
    { value: 'STIFF_MOTION', label: '动作僵硬' },
    { value: 'CAMERA_TOO_FAST', label: '运镜太快' },
    { value: 'CHAOTIC_EDITING', label: '切镜混乱' },
    { value: 'PRODUCT_UNCLEAR', label: '商品展示不足' },
  ],
}

export function toggleFeedbackReason(
  selected: FeedbackReason[],
  reason: FeedbackReason,
  limit = 3,
): FeedbackReason[] {
  if (selected.includes(reason)) return selected.filter((item) => item !== reason)
  if (selected.length >= limit) return selected
  return [...selected, reason]
}
