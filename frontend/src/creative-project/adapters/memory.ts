import type {
  CreativeMemory,
  CreativeMemoryEntry,
  CreativeMemoryQuery,
} from '../memory'
import { assertCreativeMemoryEntry } from '../memorySchema'

function cloneEntry(entry: CreativeMemoryEntry): CreativeMemoryEntry {
  return structuredClone(entry)
}

function matchesQuery(entry: CreativeMemoryEntry, query: CreativeMemoryQuery): boolean {
  return entry.projectId === query.projectId
    && (query.kind === undefined || entry.kind === query.kind)
    && (query.from === undefined || entry.occurredAt >= query.from)
    && (query.to === undefined || entry.occurredAt <= query.to)
}

export class InMemoryCreativeMemoryAdapter implements CreativeMemory {
  private readonly entries = new Map<string, CreativeMemoryEntry>()

  async append(entry: CreativeMemoryEntry): Promise<CreativeMemoryEntry> {
    assertCreativeMemoryEntry(entry)
    if (this.entries.has(entry.id)) throw new Error(`Creative Memory entry already exists: ${entry.id}`)
    const stored = cloneEntry(entry)
    this.entries.set(stored.id, stored)
    return cloneEntry(stored)
  }

  async list(query: CreativeMemoryQuery): Promise<readonly CreativeMemoryEntry[]> {
    return [...this.entries.values()]
      .filter((entry) => matchesQuery(entry, query))
      .sort((left, right) => left.occurredAt.localeCompare(right.occurredAt)
        || left.recordedAt.localeCompare(right.recordedAt)
        || left.id.localeCompare(right.id))
      .map(cloneEntry)
  }

  async get(projectId: string, entryId: string): Promise<CreativeMemoryEntry | null> {
    const entry = this.entries.get(entryId)
    return entry?.projectId === projectId ? cloneEntry(entry) : null
  }
}
