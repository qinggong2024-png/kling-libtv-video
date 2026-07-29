const SUPPORTED_IMAGE_MIME_TYPES = new Set([
  'image/jpeg',
  'image/jpg',
  'image/png',
  'image/webp',
])

const SUPPORTED_IMAGE_EXTENSION = /\.(?:jpe?g|png|webp)$/i

export const IMAGE_FILE_ACCEPT = '.jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp'

export function isSupportedImageFile(file: Pick<File, 'name' | 'type'>): boolean {
  const mimeType = file.type.trim().toLowerCase()
  return SUPPORTED_IMAGE_MIME_TYPES.has(mimeType) || SUPPORTED_IMAGE_EXTENSION.test(file.name)
}
