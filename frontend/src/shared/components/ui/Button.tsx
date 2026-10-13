import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { LoaderCircle } from 'lucide-react'

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost'
  busy?: boolean
  icon?: ReactNode
}

export function Button({ variant = 'secondary', busy = false, icon, children, className = '', disabled, type = 'button', ...props }: Props) {
  return <button {...props} type={type} disabled={disabled || busy} aria-busy={busy || props['aria-busy'] || undefined} className={`studio-button studio-button--${variant} ${className}`}>
    {busy ? <LoaderCircle className="spin" size={16} aria-hidden="true" /> : icon}
    {children}
  </button>
}

export function IconButton({ label, children, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return <Button {...props} aria-label={label} title={label} className={`studio-icon-button ${props.className ?? ''}`}>{children}</Button>
}
