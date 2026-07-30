import { describe, expect, it } from 'vitest'
import {
  stripDataUrlPrefix,
  validateKlingElementImages,
  validateKlingElementVideoUrl,
} from './klingElementFiles'

const image = (name: string, type = 'image/jpeg', size = 1024) => ({ name, type, size })

describe('Kling element references', () => {
  it('requires one to four JPG or PNG images within size limits', () => {
    expect(validateKlingElementImages([])).toContain('1–4')
    expect(validateKlingElementImages([image('front.jpg')])).toBe('')
    expect(validateKlingElementImages([image('front.jpg'), image('side.png', 'image/png')])).toBe('')
    expect(validateKlingElementImages([image('front.webp', 'image/webp'), image('side.jpg')])).toContain('JPG')
    expect(validateKlingElementImages([image('front.jpg', 'image/jpeg', 11 * 1024 * 1024), image('side.jpg')])).toContain('10 MB')
  })

  it('accepts only safe HTTPS video references', () => {
    expect(validateKlingElementVideoUrl('https://cdn.example.com/reference.mp4')).toBe('')
    expect(validateKlingElementVideoUrl('http://cdn.example.com/reference.mp4')).toContain('HTTPS')
    expect(validateKlingElementVideoUrl('not-a-url')).toContain('完整有效')
  })

  it('removes the data URL prefix without exposing it to callers', () => {
    expect(stripDataUrlPrefix('data:image/png;base64,ZmFrZS1ieXRlcw==')).toBe('ZmFrZS1ieXRlcw==')
    expect(() => stripDataUrlPrefix('ZmFrZS1ieXRlcw==')).toThrow('格式无效')
  })
})
