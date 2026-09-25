import { afterEach, describe, expect, it, vi } from 'vitest'
import { readJsonStorage, readStorage, removeStorage, writeJsonStorage, writeStorage } from './safeStorage'

/** 一个最小可用的 Storage 替身，可按需让某个方法抛异常。 */
function fakeStore(options: { onGet?: () => never; onSet?: () => never } = {}): Storage {
  const data = new Map<string, string>()
  return {
    get length() { return data.size },
    clear: () => data.clear(),
    getItem: (key: string) => {
      if (options.onGet) options.onGet()
      return data.get(key) ?? null
    },
    key: (index: number) => [...data.keys()][index] ?? null,
    removeItem: (key: string) => { data.delete(key) },
    setItem: (key: string, value: string) => {
      if (options.onSet) options.onSet()
      data.set(key, value)
    },
  } as Storage
}

/** 模拟隐私模式：读取 globalThis.localStorage 这个属性本身就抛 SecurityError。 */
function defineThrowingStorage(name: 'localStorage' | 'sessionStorage') {
  Object.defineProperty(globalThis, name, {
    configurable: true,
    get() { throw new Error(`SecurityError: ${name} is not available in this context`) },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
  // node 环境本就没有这两个属性，删除即可恢复原状。
  delete (globalThis as Record<string, unknown>).localStorage
  delete (globalThis as Record<string, unknown>).sessionStorage
})

describe('safeStorage', () => {
  it('round-trips plain strings', () => {
    vi.stubGlobal('localStorage', fakeStore())
    expect(writeStorage('local', 'k', 'v')).toBe(true)
    expect(readStorage('local', 'k')).toBe('v')
  })

  it('round-trips JSON values', () => {
    vi.stubGlobal('localStorage', fakeStore())
    expect(writeJsonStorage('local', 'k', { a: 1 })).toBe(true)
    expect(readJsonStorage('local', 'k', {})).toEqual({ a: 1 })
  })

  it('keeps local and session storage separate', () => {
    vi.stubGlobal('localStorage', fakeStore())
    vi.stubGlobal('sessionStorage', fakeStore())
    writeStorage('local', 'k', 'local-value')
    expect(readStorage('session', 'k')).toBeNull()
  })

  it('returns null instead of throwing when the read itself fails', () => {
    vi.stubGlobal('localStorage', fakeStore({ onGet: () => { throw new Error('QuotaExceededError') } }))
    expect(() => readStorage('local', 'k')).not.toThrow()
    expect(readStorage('local', 'k')).toBeNull()
  })

  it('reports failure instead of throwing when the write fails', () => {
    vi.stubGlobal('localStorage', fakeStore({ onSet: () => { throw new Error('QuotaExceededError') } }))
    expect(writeStorage('local', 'k', 'v')).toBe(false)
    expect(writeJsonStorage('local', 'k', { a: 1 })).toBe(false)
  })

  it('degrades when the storage property itself is inaccessible', () => {
    defineThrowingStorage('localStorage')
    expect(readStorage('local', 'k')).toBeNull()
    expect(writeStorage('local', 'k', 'v')).toBe(false)
    expect(writeJsonStorage('local', 'k', { a: 1 })).toBe(false)
    expect(() => removeStorage('local', 'k')).not.toThrow()
  })

  it('falls back when the stored JSON is missing, empty, or corrupted', () => {
    const store = fakeStore()
    vi.stubGlobal('localStorage', store)

    expect(readJsonStorage('local', 'missing', { fallback: true })).toEqual({ fallback: true })

    store.setItem('empty', '')
    expect(readJsonStorage('local', 'empty', { fallback: true })).toEqual({ fallback: true })

    store.setItem('corrupted', '{not json')
    expect(readJsonStorage('local', 'corrupted', { fallback: true })).toEqual({ fallback: true })
  })

  it('removes one or many keys', () => {
    const store = fakeStore()
    vi.stubGlobal('localStorage', store)
    store.setItem('a', '1')
    store.setItem('b', '2')

    removeStorage('local', 'a')
    expect(readStorage('local', 'a')).toBeNull()

    removeStorage('local', ['b'])
    expect(readStorage('local', 'b')).toBeNull()
  })

  it('is inert when no storage exists at all', () => {
    // node 环境没有 localStorage / sessionStorage，等同于完全不支持存储的宿主。
    expect(readStorage('local', 'k')).toBeNull()
    expect(writeStorage('session', 'k', 'v')).toBe(false)
    expect(readJsonStorage('session', 'k', [])).toEqual([])
  })
})
