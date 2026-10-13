import { readJsonStorage, removeStorage, writeJsonStorage } from '../safeStorage'
import type { CreativeProject } from './types'

const STORAGE_PREFIX = 'libtv:creative-project:v1:'

function storageKey(projectId: string): string {
  return `${STORAGE_PREFIX}${encodeURIComponent(projectId)}`
}

function isTransientValue(value: unknown, key?: string): boolean {
  if (key && /(?:file|blob|filelist)$/i.test(key)) return true
  if (typeof File !== 'undefined' && value instanceof File) return true
  if (typeof Blob !== 'undefined' && value instanceof Blob) return true
  return false
}

function jsonSafe(value: unknown, key?: string): unknown {
  if (isTransientValue(value, key)) return undefined
  if (Array.isArray(value)) {
    return value.map((item) => jsonSafe(item)).filter((item) => item !== undefined)
  }
  if (value && typeof value === 'object') {
    const output: Record<string, unknown> = {}
    for (const [childKey, childValue] of Object.entries(value)) {
      const safeValue = jsonSafe(childValue, childKey)
      if (safeValue !== undefined) output[childKey] = safeValue
    }
    return output
  }
  if (typeof value === 'function' || typeof value === 'symbol') return undefined
  return value
}

function isProjectSnapshot(value: unknown, projectId: string): value is CreativeProject {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Partial<CreativeProject>
  return candidate.id === projectId && Array.isArray(candidate.assets)
}

export function readPersistedCreativeProject(initialProject: CreativeProject): CreativeProject {
  const stored = readJsonStorage<unknown>('local', storageKey(initialProject.id), null)
  return isProjectSnapshot(stored, initialProject.id)
    ? { ...initialProject, ...stored }
    : initialProject
}

export function persistCreativeProject(project: CreativeProject): boolean {
  const snapshot = jsonSafe(project)
  return writeJsonStorage('local', storageKey(project.id), snapshot)
}

export function clearPersistedCreativeProject(projectId: string): void {
  removeStorage('local', storageKey(projectId))
}
