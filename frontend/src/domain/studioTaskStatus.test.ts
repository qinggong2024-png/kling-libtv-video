import { describe, expect, it } from 'vitest'
import type { Task, Variant } from '../types'
import { studioTaskPresentation } from './studioTaskStatus'

const task = (phase: string, variants: Partial<Variant>[] = []) => ({
  phase, phaseReasonCode: null, variants,
  actionCapabilities: { canConfirm: false, canDownload: false, canRetryAnalysis: false },
}) as Task

describe('studio task lifecycle', () => {
  it.each([
    ['QUEUED', 'queued'], ['DRAFT', 'preparing'], ['ANALYZING', 'preparing'],
    ['PREPARING', 'preparing'], ['WAITING_FOR_SEAL', 'preparing'],
    ['GENERATING', 'running'], ['DOWNLOADING', 'validation'], ['VALIDATING', 'validation'],
    ['DELIVERABLE', 'completed'], ['ACTION_REQUIRED', 'failed'],
  ])('maps %s without mutating the server phase', (phase, status) => {
    const source = task(phase)
    expect(studioTaskPresentation(source).status).toBe(status)
    expect(source.phase).toBe(phase)
  })

  it.each(['CANCELLED', 'AWAITING_CONFIRMATION', 'AWAITING_FINAL_APPROVAL', 'PARTIALLY_DELIVERABLE', 'NEW_SERVER_PHASE'])('keeps exceptional %s outside normal six states', (phase) => {
    expect(studioTaskPresentation(task(phase)).status).toBeNull()
  })

  it.each(['GENERATING', 'DELIVERABLE', 'ACTION_REQUIRED'])('an UNKNOWN attempt overrides %s including its label', (phase) => {
    const presentation = studioTaskPresentation(task(phase, [{ generationStatus: 'UNKNOWN' }]))
    expect(presentation).toMatchObject({ status: null, semantic: 'unknown', tone: 'warning', primaryAction: 'RECONCILE' })
    expect(presentation.label).not.toBe('已完成')
  })
})
