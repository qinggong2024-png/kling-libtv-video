import { useCallback, useEffect, useState } from 'react'
import { preserveProjectQuery } from '../../app/productNavigation'

export type ImageStudioView = 'home' | 'image-to-image' | 'text-to-image' | 'batch' | 'batch-create' | 'batch-products' | 'batch-storyboard' | 'records'

export function readImageStudioView(search: string): ImageStudioView {
  const value = new URLSearchParams(search).get('imageMode')
  return value === 'image-to-image' || value === 'text-to-image' || value === 'batch'
    || value === 'batch-create' || value === 'batch-products' || value === 'batch-storyboard' || value === 'records'
    ? value
    : 'home'
}

export function useImageStudioNavigation(): {
  view: ImageStudioView
  navigate: (next: ImageStudioView, replace?: boolean) => void
} {
  const [view, setView] = useState<ImageStudioView>(() => readImageStudioView(window.location.search))

  useEffect(() => {
    const restoreView = () => setView(readImageStudioView(window.location.search))
    window.addEventListener('popstate', restoreView)
    window.addEventListener('app:navigation', restoreView)
    return () => {
      window.removeEventListener('popstate', restoreView)
      window.removeEventListener('app:navigation', restoreView)
    }
  }, [])

  const navigate = useCallback((next: ImageStudioView, replace = false) => {
    const params = preserveProjectQuery(new URLSearchParams({ view: 'images', pane: 'image' }))
    if (next !== 'home') params.set('imageMode', next)
    window.history[replace ? 'replaceState' : 'pushState'](null, '', `${window.location.pathname}?${params.toString()}`)
    window.dispatchEvent(new Event('app:navigation'))
    setView(next)
    window.scrollTo({ top: 0, behavior: 'auto' })
  }, [])

  return { view, navigate }
}
