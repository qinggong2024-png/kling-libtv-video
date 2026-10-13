import { describe, expect, it } from 'vitest'
import { createDirectorSpatialPlan, setKeyVisualDecision } from './spatialPlanning'
import { defaultDirectorDirections } from './directorModel'

describe('Director spatial planning', () => {
  it('creates a qualitative floor plan, camera axis and actor paths without claiming measured evidence', () => {
    const plan = createDirectorSpatialPlan(defaultDirectorDirections[0])
    expect(plan.schemaVersion).toBe('1.13.7')
    expect(plan.sceneFloorPlan.anchors).toHaveLength(2)
    expect(plan.sceneFloorPlan.units).toBe('qualitative_zones')
    expect(plan.sceneFloorPlan.status).toBe('planned_not_verified')
    expect(plan.cameraBlocking.positions.map((camera) => camera.cameraId)).toEqual(['C1', 'C2', 'C3'])
    expect(plan.actorBlocking[1].movementPath).toContain('开放通道')
    expect(plan.keyVisualPlan.keyVisualCount).toBe(4)
    expect(plan.keyVisualPlan.plannedImageCount).toBe(3)
    expect(plan.keyVisualPlan.authorizedImageCount).toBe(0)
    expect(plan.keyVisualPlan.generatedImageCount).toBe(0)
  })

  it('recounts key visuals when a frame is merged without changing authorization or generation state', () => {
    const plan = createDirectorSpatialPlan(defaultDirectorDirections[0])
    const next = setKeyVisualDecision(plan, 'K04', 'merge')
    expect(next.keyVisualPlan.keyVisualCount).toBe(3)
    expect(next.keyVisualPlan.plannedImageCount).toBe(3)
    expect(next.keyVisualPlan.authorizedImageCount).toBe(0)
    expect(next.keyVisualPlan.generatedImageCount).toBe(0)
    expect(next.keyVisualPlan.frames.find((frame) => frame.keyId === 'K04')?.decision).toBe('merge')
  })
})
