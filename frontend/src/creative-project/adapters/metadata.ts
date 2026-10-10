import type { CreativeProject } from '../types'

export function mergeProjectMetadata(
  project: CreativeProject,
  metadata: Record<string, unknown>,
): CreativeProject {
  return {
    ...project,
    metadata: {
      ...project.metadata,
      ...metadata,
    },
    revision: (project.revision ?? 0) + 1,
  }
}
