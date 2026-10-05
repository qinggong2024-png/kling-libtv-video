import type { ImageCenterDraft } from './imageCenterModel'

const DATABASE_NAME = 'clothing-production-image-center'
const DATABASE_VERSION = 1
const STORE_NAME = 'drafts'
const DRAFT_KEY_PREFIX = 'image-center:v2:'

export function imageCenterDraftKey(accountScope: string | null | undefined): string | null {
  const normalized = accountScope?.trim()
  return normalized ? `${DRAFT_KEY_PREFIX}${normalized}` : null
}

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION)
    request.onerror = () => reject(request.error ?? new Error('图片中心草稿数据库打开失败'))
    request.onupgradeneeded = () => {
      const database = request.result
      if (!database.objectStoreNames.contains(STORE_NAME)) database.createObjectStore(STORE_NAME)
    }
    request.onsuccess = () => resolve(request.result)
  })
}

export async function loadImageCenterDraft(accountScope: string | null | undefined): Promise<ImageCenterDraft | null> {
  const key = imageCenterDraftKey(accountScope)
  if (!key || !('indexedDB' in globalThis)) return null
  const database = await openDatabase()
  return new Promise((resolve, reject) => {
    const transaction = database.transaction(STORE_NAME, 'readonly')
    const request = transaction.objectStore(STORE_NAME).get(key)
    request.onerror = () => reject(request.error ?? new Error('图片中心草稿读取失败'))
    request.onsuccess = () => resolve((request.result as ImageCenterDraft | undefined) ?? null)
    transaction.oncomplete = () => database.close()
  })
}

export async function saveImageCenterDraft(accountScope: string | null | undefined, draft: ImageCenterDraft): Promise<void> {
  const key = imageCenterDraftKey(accountScope)
  if (!key || !('indexedDB' in globalThis)) return
  const database = await openDatabase()
  return new Promise((resolve, reject) => {
    const transaction = database.transaction(STORE_NAME, 'readwrite')
    transaction.objectStore(STORE_NAME).put(draft, key)
    transaction.onerror = () => reject(transaction.error ?? new Error('图片中心草稿保存失败'))
    transaction.oncomplete = () => {
      database.close()
      resolve()
    }
  })
}

