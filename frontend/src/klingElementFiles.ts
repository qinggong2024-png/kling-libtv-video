export const KLING_ELEMENT_MIN_IMAGES = 2
export const KLING_ELEMENT_MAX_IMAGES = 4
export const KLING_ELEMENT_MAX_IMAGE_BYTES = 10 * 1024 * 1024
export const KLING_ELEMENT_MAX_TOTAL_IMAGE_BYTES = 40 * 1024 * 1024

type ImageFileCandidate = Pick<File, 'name' | 'size' | 'type'>

export function validateKlingElementImages(files: ImageFileCandidate[]): string {
  if (files.length < KLING_ELEMENT_MIN_IMAGES || files.length > KLING_ELEMENT_MAX_IMAGES) {
    return `图像主体需要 ${KLING_ELEMENT_MIN_IMAGES}–${KLING_ELEMENT_MAX_IMAGES} 张参考图。`
  }
  const unsupported = files.find((file) => !['image/jpeg', 'image/png'].includes(file.type.toLowerCase()))
  if (unsupported) return `“${unsupported.name}”不是支持的 JPG 或 PNG 图片。`
  const oversized = files.find((file) => file.size > KLING_ELEMENT_MAX_IMAGE_BYTES)
  if (oversized) return `“${oversized.name}”超过 10 MB 单文件上限。`
  const total = files.reduce((sum, file) => sum + file.size, 0)
  if (total > KLING_ELEMENT_MAX_TOTAL_IMAGE_BYTES) return '参考图总大小不能超过 40 MB。'
  return ''
}

export function validateKlingElementVideoUrl(value: string): string {
  const normalized = value.trim()
  if (!normalized) return '请输入视频主体的 HTTPS URL。'
  try {
    const url = new URL(normalized)
    if (url.protocol !== 'https:' || url.username || url.password || url.hash) {
      return '视频主体必须使用无账号信息和片段的 HTTPS URL。'
    }
    return ''
  } catch {
    return '请输入完整有效的视频 HTTPS URL。'
  }
}

export function stripDataUrlPrefix(value: string): string {
  const separator = value.indexOf(',')
  if (!value.startsWith('data:') || separator < 0) throw new Error('图片读取结果格式无效')
  const encoded = value.slice(separator + 1)
  if (!encoded) throw new Error('图片读取结果为空')
  return encoded
}

export function readKlingElementImage(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(new Error(`无法读取“${file.name}”`))
    reader.onload = () => {
      try {
        if (typeof reader.result !== 'string') throw new Error('图片读取结果格式无效')
        resolve(stripDataUrlPrefix(reader.result))
      } catch (cause) {
        reject(cause)
      }
    }
    reader.readAsDataURL(file)
  })
}
