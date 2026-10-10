import { createContext } from 'react'
import type { CreativeProject } from './types'

export interface CreativeProjectContextValue {
  project: CreativeProject
  replaceProject: (project: CreativeProject) => void
  updateProject: (patch: Partial<CreativeProject>) => void
}

export const CreativeProjectContext = createContext<CreativeProjectContextValue | null>(null)
