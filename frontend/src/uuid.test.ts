import { afterEach, describe, expect, it, vi } from 'vitest'
import { createUuid } from './uuid'

describe('createUuid', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('uses the native implementation when it is available', () => {
    const randomUUID = vi.fn(() => '12345678-1234-4123-8123-123456789abc')
    vi.stubGlobal('crypto', { randomUUID, getRandomValues: vi.fn() })

    expect(createUuid()).toBe('12345678-1234-4123-8123-123456789abc')
    expect(randomUUID).toHaveBeenCalledOnce()
  })

  it('creates an RFC 4122 v4 UUID when randomUUID is unavailable on LAN HTTP', () => {
    vi.stubGlobal('crypto', {
      getRandomValues: (bytes: Uint8Array) => {
        bytes.set(Array.from({ length: 16 }, (_value, index) => index))
        return bytes
      },
    })

    expect(createUuid()).toBe('00010203-0405-4607-8809-0a0b0c0d0e0f')
  })

  it('falls back when a browser exposes randomUUID but rejects it on HTTP', () => {
    vi.stubGlobal('crypto', {
      randomUUID: () => { throw new DOMException('Secure context required', 'SecurityError') },
      getRandomValues: (bytes: Uint8Array) => {
        bytes.fill(0xff)
        return bytes
      },
    })

    expect(createUuid()).toBe('ffffffff-ffff-4fff-bfff-ffffffffffff')
  })

  it('reports unsupported legacy browsers clearly', () => {
    vi.stubGlobal('crypto', {})
    expect(() => createUuid()).toThrow('当前浏览器不支持安全随机数')
  })
})
