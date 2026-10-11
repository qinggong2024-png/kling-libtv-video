import { describe, expect, it } from 'vitest'
import { canReviewDirectorCandidate, canSelectDirectorCandidate, createDirectorDraft, directionsFromAnalysis, isDirectorIntakeReady, selectDirectorDirection } from './directorModel'
import type { DirectorCandidate, DirectorTaskResponse } from './directorApi'

describe('Director Studio planning model', () => {
  it('starts with an explicit intake boundary and three candidate directions', () => {
    const draft = createDirectorDraft()
    expect(draft.phase).toBe('intake')
    expect(draft.directions.map((direction) => direction.id)).toEqual(['A', 'B', 'C'])
    expect(isDirectorIntakeReady(draft.intake)).toBe(false)
  })

  it('selects a direction without creating a generation task', () => {
    const draft = createDirectorDraft()
    const next = selectDirectorDirection(draft, 'B')
    expect(next.phase).toBe('package')
    expect(next.selectedDirectionId).toBe('B')
    expect('taskId' in next).toBe(false)
  })

  it('requires a product front before planning can begin', () => {
    const draft = createDirectorDraft()
    expect(isDirectorIntakeReady({ ...draft.intake, productFrontName: 'front.jpg' })).toBe(true)
  })

  it('maps server analysis into the stable A/B/C presentation model', () => {
    const directions = directionsFromAnalysis([
      { id: 'A', scene: 'plain studio', behavior: 'standing still' },
      { id: 'B', scene: 'indoor room', behavior: 'seated casually' },
      { id: 'C', scene: 'outdoor walkway', behavior: 'walking slowly' },
    ])
    expect(directions.map((direction) => direction.id)).toEqual(['A', 'B', 'C'])
    expect(directions[1].summary).toBe('indoor room，seated casually。')
  })
})

describe('Director offline review boundary', () => {
  const candidate = {
    candidate_id: 'candidate-1', package_id: 'package-1', shot_id: 'FIRST_FRAME',
    synthetic: true, qualified: false,
  } as DirectorCandidate
  const workflow = {
    id: 'task-1', mode: 'OFFLINE_FAKE_ONLY', status: 'IMAGE_REVIEW',
    snapshot: { package: { package_id: 'package-1' }, candidates: [candidate] },
  } as DirectorTaskResponse

  it('requires a distinct human review before selecting and does not mutate qualification', () => {
    expect(canReviewDirectorCandidate(workflow, candidate)).toBe(true)
    expect(canSelectDirectorCandidate(workflow, candidate)).toBe(false)
    expect(canSelectDirectorCandidate(workflow, { ...candidate, qualified: true })).toBe(true)
    expect(candidate.qualified).toBe(false)
  })

  it.each(['UNKNOWN', 'WRITE_UNCERTAIN'])('blocks review and selection for %s execution', (execution_state) => {
    const uncertain = { ...workflow, snapshot: { ...workflow.snapshot, execution_state } }
    expect(canReviewDirectorCandidate(uncertain, candidate)).toBe(false)
    expect(canSelectDirectorCandidate(uncertain, { ...candidate, qualified: true })).toBe(false)
  })

  it('blocks stopped, wrong-stage and non-offline tasks', () => {
    expect(canReviewDirectorCandidate({ ...workflow, snapshot: { ...workflow.snapshot, stopped: true } }, candidate)).toBe(false)
    expect(canReviewDirectorCandidate({ ...workflow, status: 'BLOCKED' }, candidate)).toBe(false)
    expect(canReviewDirectorCandidate({ ...workflow, mode: 'REAL_PROVIDER' }, candidate)).toBe(false)
  })

  it('blocks stale packages, wrong shots and non-synthetic candidates even if marked qualified', () => {
    for (const patch of [{ package_id: 'old-package' }, { shot_id: 'shot-2' }, { synthetic: false }]) {
      expect(canSelectDirectorCandidate(workflow, { ...candidate, ...patch, qualified: true })).toBe(false)
    }
  })
})
