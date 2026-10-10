import type { CreativeIntelligenceSnapshot } from './types'

export type CreativeMemoryEntryKind =
  | 'creative-decision'
  | 'direction'
  | 'generated-output'
  | 'analysis-reference'

export interface CreativeMemoryEntry {
  id: string
  projectId: string
  kind: CreativeMemoryEntryKind
  createdAt: string
  payload: Record<string, unknown>
  intelligenceSnapshot?: CreativeIntelligenceSnapshot
}

export interface CreativeMemoryQuery {
  projectId: string
  kind?: CreativeMemoryEntryKind
}

export interface CreativeMemoryReader {
  list(query: CreativeMemoryQuery): Promise<readonly CreativeMemoryEntry[]>
  get(projectId: string, entryId: string): Promise<CreativeMemoryEntry | null>
}

export interface CreativeMemoryWriter {
  append(entry: CreativeMemoryEntry): Promise<CreativeMemoryEntry>
}

export interface CreativeMemory extends CreativeMemoryReader, CreativeMemoryWriter {}
