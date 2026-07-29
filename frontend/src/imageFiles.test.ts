import { describe, expect, it } from 'vitest'
import { IMAGE_FILE_ACCEPT, isSupportedImageFile } from './imageFiles'

describe('image file selection', () => {
  it.each([
    ['standard JPEG MIME', 'photo.bin', 'image/jpeg'],
    ['alternate JPEG MIME', 'photo.bin', 'image/jpg'],
    ['empty MIME with a JPEG extension', 'photo.JPG', ''],
    ['generic MIME with a PNG extension', 'frame.png', 'application/octet-stream'],
    ['WebP extension', 'product.webp', ''],
  ])('accepts %s', (_label, name, type) => {
    expect(isSupportedImageFile({ name, type })).toBe(true)
  })

  it.each([
    ['photo.heic', 'image/heic'],
    ['notes.pdf', 'application/pdf'],
    ['unknown', ''],
  ])('rejects unsupported file %s', (name, type) => {
    expect(isSupportedImageFile({ name, type })).toBe(false)
  })

  it('advertises both extensions and browser MIME types', () => {
    expect(IMAGE_FILE_ACCEPT).toContain('.jpg')
    expect(IMAGE_FILE_ACCEPT).toContain('.webp')
    expect(IMAGE_FILE_ACCEPT).toContain('image/jpeg')
  })
})
