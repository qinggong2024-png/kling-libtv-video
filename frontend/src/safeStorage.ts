/**
 * localStorage / sessionStorage 的安全封装。
 *
 * 直接用 `localStorage.getItem(...)` 并不安全：浏览器会在下面这几种**常态**下抛异常——
 * - 隐私模式 / 站点数据被禁用：连读取 `globalThis.localStorage` 这个属性本身都可能抛 SecurityError
 * - 配额写满（QuotaExceededError），Safari 隐私模式尤其常见
 * - 第三方 Cookie 被阻断的 iframe 环境
 *
 * 而项目里这些调用点存的全是 UI 偏好（收起了哪些提醒、开发视角选的是管理员还是普通用户）。
 * 偏好丢了最多让界面回到默认值，但抛异常会顺着 React 渲染树一路冒泡、整页白屏。
 * 所以这里统一降级：读失败返回兜底值，写失败静默忽略。
 */

export type StorageKind = 'local' | 'session'

function storageFor(kind: StorageKind): Storage | null {
  try {
    return kind === 'local' ? globalThis.localStorage : globalThis.sessionStorage
  } catch {
    // 隐私模式下访问该属性本身就会抛 SecurityError。
    return null
  }
}

/** 读取字符串；存储不可用或读取抛异常时返回 null。 */
export function readStorage(kind: StorageKind, key: string): string | null {
  try {
    return storageFor(kind)?.getItem(key) ?? null
  } catch {
    return null
  }
}

/** 读取并解析 JSON；内容缺失、为空串或已损坏时返回 fallback。 */
export function readJsonStorage<T>(kind: StorageKind, key: string, fallback: T): T {
  const raw = readStorage(kind, key)
  if (raw === null || raw === '') return fallback
  try {
    return JSON.parse(raw) as T
  } catch {
    return fallback
  }
}

/** 写入字符串；配额写满或存储不可用时返回 false（调用方通常无需处理）。 */
export function writeStorage(kind: StorageKind, key: string, value: string): boolean {
  try {
    const api = storageFor(kind)
    if (!api) return false
    api.setItem(key, value)
    return true
  } catch {
    return false
  }
}

/** 序列化后写入；序列化失败或写入失败返回 false。 */
export function writeJsonStorage(kind: StorageKind, key: string, value: unknown): boolean {
  let serialized: string
  try {
    serialized = JSON.stringify(value)
  } catch {
    return false
  }
  return writeStorage(kind, key, serialized)
}

/** 尽力移除一个或多个键；存储不可用时静默跳过。 */
export function removeStorage(kind: StorageKind, keys: string | readonly string[]): void {
  const list = typeof keys === 'string' ? [keys] : keys
  try {
    const api = storageFor(kind)
    if (!api) return
    for (const key of list) api.removeItem(key)
  } catch {
    // 清理失败不影响主流程。
  }
}
