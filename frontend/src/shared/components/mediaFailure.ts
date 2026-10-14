// 媒体读取失败的分级规则（与组件分离，供 Media / ResultCard / 结果区共享）。
//
// 背景：接口在维护模式下会对缩略图/视频统一返回 503，过去 `AuthenticatedImage` 只用布尔 `failed`
// 记录失败，把 `ApiError.status` 丢掉了，页面上只剩「图片不可用」一句灰字 —— 用户无法区分
// 「本来就没有图」和「服务挂了」，也没有任何补救出口。这里把状态码保留下来做分级。
import { ApiError } from '../../api'

export type MediaFailureKind = 'maintenance' | 'timeout' | 'missing' | 'forbidden' | 'network' | 'playback' | 'unknown'

export type MediaFailure = {
  kind: MediaFailureKind
  status: number | null
  /** 一句话结论，落在卡片/兜底块的主行。 */
  label: string
  /** 补充说明与下一步动作，落在次级行。 */
  detail: string
  retryable: boolean
}

export function classifyMediaFailure(cause: unknown): MediaFailure {
  const status = cause instanceof ApiError ? cause.status : null
  if (status === 502 || status === 503) {
    return {
      kind: 'maintenance',
      status,
      label: '服务维护中',
      detail: '视频与缩略图服务正在维护，这个素材暂时读不出来。稍后重试即可，已有任务不受影响。',
      retryable: true,
    }
  }
  if (status === 408 || status === 504) {
    return { kind: 'timeout', status, label: '读取超时', detail: '素材在规定时间内没有返回，通常是服务繁忙。稍后重试即可。', retryable: true }
  }
  if (status === 404 || status === 410) {
    return { kind: 'missing', status, label: '文件已失效', detail: '文件已过期或被清理，无法再查看。如需留存请从任务详情重新生成。', retryable: false }
  }
  if (status === 401 || status === 403) {
    return { kind: 'forbidden', status, label: '没有访问权限', detail: '登录状态可能已失效，重新登录后再试。', retryable: false }
  }
  if (status === null) {
    return { kind: 'network', status: null, label: '加载失败', detail: '网络中断或生产服务未响应，请检查网络后重试。', retryable: true }
  }
  return { kind: 'unknown', status, label: '加载失败', detail: `接口返回 ${status}，这个素材暂时读不出来。`, retryable: true }
}

/** 视频已经拿到 URL、但浏览器解不开时使用（编码/封装不受支持）。 */
export function playbackFailure(): MediaFailure {
  return {
    kind: 'playback',
    status: null,
    label: '视频无法播放',
    detail: '浏览器无法解码这个视频，可下载后用本地播放器打开。',
    retryable: true,
  }
}
