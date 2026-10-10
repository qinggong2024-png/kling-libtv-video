import type { CreativeProject } from './types'

export function createCreativeProject(project: Partial<CreativeProject> & Pick<CreativeProject, 'id'>): CreativeProject {
  return {
    id: project.id,
    assets: project.assets ?? [],
    ...(project.name ? { name: project.name } : {}),
    ...(project.currentStage ? { currentStage: project.currentStage } : {}),
    ...(project.metadata ? { metadata: project.metadata } : {}),
    ...(project.revision === undefined ? {} : { revision: project.revision }),
    ...(project.workflowContext ? { workflowContext: project.workflowContext } : {}),
    ...(project.intelligenceSnapshot ? { intelligenceSnapshot: project.intelligenceSnapshot } : {}),
  }
}
