import { UploadCloud } from 'lucide-react'
import type { ButtonHTMLAttributes, ReactNode } from 'react'
import './imageUploadTrigger.css'

export function ImageUploadTrigger({ title, description = 'JPG、PNG、WEBP', preview, className = '', children, ...props }: Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'title'> & {
  title: string
  description?: string
  preview?: ReactNode
}) {
  return <button {...props} type="button" className={`studio-image-upload ${className}`}>
    <span className="studio-image-upload__icon">{preview ?? <UploadCloud size={22} aria-hidden="true" />}</span>
    <span className="studio-image-upload__copy"><strong>{title}</strong><small>{description}</small></span>
    {children}
  </button>
}
