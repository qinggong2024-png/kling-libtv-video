import type { View } from './appTypes'

export type ProductSurface = 'workspace' | 'projects' | 'director' | 'image' | 'video' | 'review' | 'assets' | 'memory'

const surfaces: ProductSurface[] = ['workspace', 'projects', 'director', 'image', 'video', 'review', 'assets', 'memory']

export function readProductSurface(search: string): ProductSurface | null {
  const params = new URLSearchParams(search)
  if (params.has('task')) return null
  const pane = params.get('pane') as ProductSurface
  const surface = surfaces.includes(pane) ? pane : null
  if (!surface) return null
  const view = params.get('view') ?? 'make'
  return view === productSurfaceView(surface) ? surface : null
}

export function productSurfaceView(surface: ProductSurface): View {
  if (surface === 'director' || surface === 'image') return 'images'
  if (surface === 'review') return 'records'
  if (surface === 'assets') return 'library'
  return 'make'
}

export function preserveProjectQuery(params: URLSearchParams): URLSearchParams {
  const projectId = new URLSearchParams(window.location.search).get('project')
  if (projectId) params.set('project', projectId)
  return params
}
