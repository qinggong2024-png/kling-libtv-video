import { useContext } from 'react'
import { CreativeProjectContext } from './store'
import type { CreativeProjectContextValue } from './store'

export function useCreativeProject(): CreativeProjectContextValue {
  const context = useContext(CreativeProjectContext)
  if (!context) throw new Error('useCreativeProject must be used within CreativeProjectProvider')
  return context
}
