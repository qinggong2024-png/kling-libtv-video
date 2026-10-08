import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'

export function Modal({ labelledBy, onClose, className = '', children }: {
  labelledBy: string
  onClose: () => void
  className?: string
  children: ReactNode
}) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    const previous = document.activeElement as HTMLElement | null
    const alreadyLocked = document.body.classList.contains('overlay-open')
    document.body.classList.add('overlay-open')
    dialog.showModal()
    return () => {
      dialog.close()
      if (!alreadyLocked) document.body.classList.remove('overlay-open')
      if (previous?.isConnected) previous.focus()
    }
  }, [])
  return <dialog ref={ref} className={`studio-modal ${className}`} aria-labelledby={labelledBy} onCancel={(event) => { event.preventDefault(); onClose() }} onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>{children}</dialog>
}
