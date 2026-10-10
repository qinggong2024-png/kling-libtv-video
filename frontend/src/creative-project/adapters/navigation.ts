import type { View } from '../../app/appTypes'
import type { CreativeWorkflowContext } from '../types'

export interface CreativeNavigationSnapshot {
  search: string
  view: View
  detailId?: string | null
}

export function readProjectIdFromSearch(search: string): string | null {
  const projectId = new URLSearchParams(search).get('project')
  return projectId?.trim() || null
}

export function toCreativeWorkflowContext(snapshot: CreativeNavigationSnapshot): CreativeWorkflowContext {
  return {
    activeView: snapshot.view,
    ...(snapshot.detailId ? { activeTaskId: snapshot.detailId } : {}),
  }
}
