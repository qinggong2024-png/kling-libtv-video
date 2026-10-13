import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { readPersistedCreativeProject, persistCreativeProject } from './recovery'
import { CreativeProjectContext } from './store'
import type { CreativeProject } from './types'

export function CreativeProjectProvider({
  initialProject,
  children,
}: {
  initialProject: CreativeProject
  children: ReactNode
}) {
  const [project, setProject] = useState(() => readPersistedCreativeProject(initialProject))
  const replaceProject = useCallback((nextProject: CreativeProject) => {
    setProject(nextProject)
  }, [])
  const updateProject = useCallback((patch: Partial<CreativeProject>) => {
    setProject((current) => ({
      ...current,
      ...patch,
      ...(patch.assets ? { assets: patch.assets } : {}),
      ...(patch.metadata ? { metadata: { ...current.metadata, ...patch.metadata } } : {}),
    }))
  }, [])
  const clearProjectRecovery = useCallback(() => {
    setProject((current) => {
      const metadata = { ...current.metadata }
      delete metadata.directorPlanning
      delete metadata.directorRecovery
      const workflowContext = current.workflowContext
        ? {
            ...(current.workflowContext.activeView ? { activeView: current.workflowContext.activeView } : {}),
          }
        : undefined
      return {
        ...current,
        ...(workflowContext ? { workflowContext } : { workflowContext: undefined }),
        ...(Object.keys(metadata).length ? { metadata } : { metadata: undefined }),
        revision: (current.revision ?? 0) + 1,
      }
    })
  }, [])
  useEffect(() => {
    persistCreativeProject(project)
  }, [project])
  const value = useMemo(
    () => ({ project, replaceProject, updateProject, clearProjectRecovery }),
    [project, replaceProject, updateProject, clearProjectRecovery],
  )

  return <CreativeProjectContext.Provider value={value}>{children}</CreativeProjectContext.Provider>
}
