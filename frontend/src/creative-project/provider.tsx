import { useCallback, useMemo, useState, type ReactNode } from 'react'
import { CreativeProjectContext } from './store'
import type { CreativeProject } from './types'

export function CreativeProjectProvider({
  initialProject,
  children,
}: {
  initialProject: CreativeProject
  children: ReactNode
}) {
  const [project, setProject] = useState(initialProject)
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
  const value = useMemo(
    () => ({ project, replaceProject, updateProject }),
    [project, replaceProject, updateProject],
  )

  return <CreativeProjectContext.Provider value={value}>{children}</CreativeProjectContext.Provider>
}
