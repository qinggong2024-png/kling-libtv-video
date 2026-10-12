import type { CreativeIntelligenceSnapshot } from './types'

export type CreativeMemoryEntryKind =
  | 'direction-history'
  | 'candidate-selection'
  | 'production-package-revision'
  | 'bridge-decision'

export interface CreativeMemoryEntryBase {
  id: string
  projectId: string
  occurredAt: string
  recordedAt: string
  source: 'creative-project'
  intelligenceSnapshot?: CreativeIntelligenceSnapshot
}

export interface DirectionHistoryPayload {
  directionId: string
  action: 'created' | 'updated' | 'archived' | 'restored'
  title?: string
  summary?: string
  reason?: string
}

export interface CandidateSelectionPayload {
  candidateId: string
  decision: 'shortlisted' | 'selected' | 'rejected' | 'cleared'
  directionId?: string
  reason?: string
}

export interface ProductionPackageRevisionPayload {
  packageId: string
  revision: number
  parentPackageId: string | null
  directionId?: string
  shotId?: string
  changeSummary?: string
}

export interface BridgeDecisionPayload {
  packageId: string
  packageRevision: number
  decision: 'prepared' | 'blocked' | 'rejected' | 'handed-off'
  purpose: 'IMAGE_FIRST_FRAME' | 'VIDEO_DIRECTOR_FIXED'
  reasonCodes: readonly string[]
  providerSubmissionAllowed: false
}

export type CreativeMemoryEntry =
  | (CreativeMemoryEntryBase & {
      kind: 'direction-history'
      payload: DirectionHistoryPayload
    })
  | (CreativeMemoryEntryBase & {
      kind: 'candidate-selection'
      payload: CandidateSelectionPayload
    })
  | (CreativeMemoryEntryBase & {
      kind: 'production-package-revision'
      payload: ProductionPackageRevisionPayload
    })
  | (CreativeMemoryEntryBase & {
      kind: 'bridge-decision'
      payload: BridgeDecisionPayload
    })

export interface CreativeMemoryQuery {
  projectId: string
  kind?: CreativeMemoryEntryKind
  from?: string
  to?: string
}

export interface CreativeMemoryReader {
  list(query: CreativeMemoryQuery): Promise<readonly CreativeMemoryEntry[]>
  get(projectId: string, entryId: string): Promise<CreativeMemoryEntry | null>
}

export interface CreativeMemoryWriter {
  append(entry: CreativeMemoryEntry): Promise<CreativeMemoryEntry>
}

export interface CreativeMemory extends CreativeMemoryReader, CreativeMemoryWriter {}
