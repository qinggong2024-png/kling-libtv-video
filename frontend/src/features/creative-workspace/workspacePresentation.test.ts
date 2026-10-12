import { describe, expect, it } from 'vitest'
import { createCreativeProject } from '../../creative-project/project'
import type { Task } from '../../types'
import { presentCreativeWorkspace } from './workspacePresentation'

const handoff = {
  source: 'director-studio' as const,
  projectId: 'project-1',
  directionId: 'A' as const,
  packageId: 'package-1',
  packageRevision: 2,
  shotId: 'FIRST_FRAME' as const,
  references: {
    productFront: true,
    selectedDirection: true,
    productionPackage: true,
  },
}

const planning = {
  brief: {
    productName: 'Spring Jacket',
    brandMode: 'generic' as const,
    brandName: '',
    objective: 'Launch',
    audience: 'Urban commuters',
    notes: '',
  },
  candidates: [{
    id: 'A' as const,
    title: 'Clean city motion',
    summary: 'A clean city sequence.',
    human: 'Natural movement',
    scene: 'Transit platform',
    behavior: 'Walk and turn',
    camera: 'Handheld medium shot',
    emotion: 'Confident',
  }],
  selectedDirectionId: 'A' as const,
  productionPackage: {
    packageId: 'package-1',
    revision: 2,
    parentPackageId: null,
    locksHash: 'locks',
    factsRevision: 1,
    preservationHash: 'preservation',
    ruleset: 'creative-os',
    shotId: 'FIRST_FRAME' as const,
    prompt: 'A clean city sequence.',
    reality: [],
  },
  handoff,
}

describe('Creative Workspace presentation', () => {
  it('derives planning and preflight context without creating production state', () => {
    const project = createCreativeProject({
      id: 'project-1',
      name: 'Spring launch',
      metadata: { directorPlanning: planning },
    })
    const summary = presentCreativeWorkspace(project)

    expect(summary.status).toBe('Preflight')
    expect(summary.direction?.title).toBe('Clean city motion')
    expect(summary.pkg?.packageId).toBe('package-1')
    expect(summary.bridge).toMatchObject({
      status: 'PREFLIGHT_REQUIRED',
      executionMode: 'OFFLINE_SYNTHETIC_ONLY',
      providerSubmissionAllowed: false,
    })
    expect(summary.nextAction.surface).toBe('director')
  })

  it('keeps an unplanned project in draft and points to Director Studio', () => {
    const summary = presentCreativeWorkspace(createCreativeProject({ id: 'empty-project' }))

    expect(summary.status).toBe('Draft')
    expect(summary.steps.every((step) => step.evidenced === false)).toBe(true)
    expect(summary.nextAction.surface).toBe('director')
  })

  it('presents an uncertain linked task as blocked without changing task state', () => {
    const project = createCreativeProject({
      id: 'project-1',
      workflowContext: { activeTaskId: 'task-1' },
    })
    const task = {
      id: 'task-1',
      phase: 'DELIVERABLE',
      variants: [{ generationStatus: 'UNKNOWN', finalApprovalStatus: 'PENDING' }],
    } as Task
    const summary = presentCreativeWorkspace(project, [task])

    expect(summary.status).toBe('Blocked')
    expect(summary.nextAction.surface).toBe('review')
    expect(summary.linkedTask?.id).toBe('task-1')
    expect(task.phase).toBe('DELIVERABLE')
  })
})
