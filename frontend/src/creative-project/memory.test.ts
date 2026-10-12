import { describe, expect, it } from 'vitest'
import { InMemoryCreativeMemoryAdapter } from './adapters/memory'
import type { CreativeMemoryEntry } from './memory'
import { isCreativeMemoryEntry } from './memorySchema'

const base = {
  projectId: 'project-1',
  occurredAt: '2026-10-12T10:00:00.000Z',
  recordedAt: '2026-10-12T10:00:01.000Z',
  source: 'creative-project' as const,
}

function directionEntry(id: string, occurredAt = base.occurredAt): CreativeMemoryEntry {
  return {
    ...base,
    id,
    occurredAt,
    kind: 'direction-history',
    payload: { directionId: 'direction-a', action: 'created', title: 'Editorial motion' },
  }
}

describe('Creative Memory schema and adapter', () => {
  it('accepts the four history kinds and rejects task-owned state', () => {
    expect(isCreativeMemoryEntry(directionEntry('direction-1'))).toBe(true)
    expect(isCreativeMemoryEntry({
      ...directionEntry('invalid'),
      payload: { directionId: 'direction-a', action: 'updated', phase: 'COMPLETED' },
    })).toBe(false)
    expect(isCreativeMemoryEntry({
      ...directionEntry('invalid-top-level'),
      status: 'COMPLETED',
    })).toBe(false)
  })

  it('keeps entries project-scoped, append-only, and chronologically ordered', async () => {
    const memory = new InMemoryCreativeMemoryAdapter()
    await memory.append(directionEntry('later', '2026-10-12T10:02:00.000Z'))
    await memory.append({
      ...base,
      id: 'selection-1',
      projectId: 'project-1',
      kind: 'candidate-selection',
      payload: { candidateId: 'candidate-a', decision: 'selected', directionId: 'direction-a' },
    })
    await memory.append({ ...directionEntry('other-project'), projectId: 'project-2' })

    await expect(memory.append(directionEntry('later'))).rejects.toThrow('already exists')
    await expect(memory.list({ projectId: 'project-1' })).resolves.toMatchObject([
      { id: 'selection-1' },
      { id: 'later' },
    ])
    await expect(memory.get('project-1', 'other-project')).resolves.toBeNull()
  })

  it('records bridge decisions without enabling provider submission', async () => {
    const memory = new InMemoryCreativeMemoryAdapter()
    await memory.append({
      ...base,
      id: 'bridge-1',
      kind: 'bridge-decision',
      payload: {
        packageId: 'package-1',
        packageRevision: 2,
        decision: 'blocked',
        purpose: 'VIDEO_DIRECTOR_FIXED',
        reasonCodes: ['SERVER_VALIDATED_PACKAGE_REQUIRED'],
        providerSubmissionAllowed: false,
      },
    })

    const [entry] = await memory.list({ projectId: 'project-1', kind: 'bridge-decision' })
    expect(entry.kind).toBe('bridge-decision')
    if (entry.kind === 'bridge-decision') {
      expect(entry.payload.providerSubmissionAllowed).toBe(false)
    }
  })
})
