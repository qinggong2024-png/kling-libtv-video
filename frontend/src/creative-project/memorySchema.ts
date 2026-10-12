import type {
  BridgeDecisionPayload,
  CandidateSelectionPayload,
  CreativeMemoryEntry,
  DirectionHistoryPayload,
  ProductionPackageRevisionPayload,
} from './memory'

const forbiddenKeys = new Set([
  'phase',
  'status',
  'stateVersion',
  'providerStatus',
  'providerTaskId',
  'billingStatus',
  'quota',
  'ledger',
])

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isIsoTimestamp(value: unknown): value is string {
  return typeof value === 'string' && !Number.isNaN(Date.parse(value))
}

function hasForbiddenKey(value: Record<string, unknown>): boolean {
  return Object.keys(value).some((key) => forbiddenKeys.has(key))
}

function isDirectionHistoryPayload(value: unknown): value is DirectionHistoryPayload {
  if (!isRecord(value) || typeof value.directionId !== 'string') return false
  return value.action === 'created'
    || value.action === 'updated'
    || value.action === 'archived'
    || value.action === 'restored'
}

function isCandidateSelectionPayload(value: unknown): value is CandidateSelectionPayload {
  if (!isRecord(value) || typeof value.candidateId !== 'string') return false
  return value.decision === 'shortlisted'
    || value.decision === 'selected'
    || value.decision === 'rejected'
    || value.decision === 'cleared'
}

function isProductionPackageRevisionPayload(
  value: unknown,
): value is ProductionPackageRevisionPayload {
  if (!isRecord(value) || typeof value.packageId !== 'string') return false
  return typeof value.revision === 'number'
    && Number.isInteger(value.revision)
    && value.revision >= 1
    && (value.parentPackageId === null || typeof value.parentPackageId === 'string')
}

function isBridgeDecisionPayload(value: unknown): value is BridgeDecisionPayload {
  if (!isRecord(value) || typeof value.packageId !== 'string') return false
  return typeof value.packageRevision === 'number'
    && Number.isInteger(value.packageRevision)
    && value.packageRevision >= 1
    && (value.decision === 'prepared'
      || value.decision === 'blocked'
      || value.decision === 'rejected'
      || value.decision === 'handed-off')
    && (value.purpose === 'IMAGE_FIRST_FRAME' || value.purpose === 'VIDEO_DIRECTOR_FIXED')
    && Array.isArray(value.reasonCodes)
    && value.reasonCodes.every((reason) => typeof reason === 'string')
    && value.providerSubmissionAllowed === false
}

export function isCreativeMemoryEntry(value: unknown): value is CreativeMemoryEntry {
  if (!isRecord(value)
    || typeof value.id !== 'string'
    || typeof value.projectId !== 'string'
    || value.source !== 'creative-project'
    || !isIsoTimestamp(value.occurredAt)
    || !isIsoTimestamp(value.recordedAt)
    || hasForbiddenKey(value)) {
    return false
  }

  if (!isRecord(value.payload) || hasForbiddenKey(value.payload)) return false
  switch (value.kind) {
    case 'direction-history':
      return isDirectionHistoryPayload(value.payload)
    case 'candidate-selection':
      return isCandidateSelectionPayload(value.payload)
    case 'production-package-revision':
      return isProductionPackageRevisionPayload(value.payload)
    case 'bridge-decision':
      return isBridgeDecisionPayload(value.payload)
    default:
      return false
  }
}

export function assertCreativeMemoryEntry(value: unknown): asserts value is CreativeMemoryEntry {
  if (!isCreativeMemoryEntry(value)) {
    throw new Error('Invalid Creative Memory entry')
  }
}
