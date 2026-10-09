import { ChevronDown, PackageOpen } from 'lucide-react'
import type { ReactNode } from 'react'

export function SubjectDisclosure({ status, initiallyOpen = false, children }: {
  status: string
  initiallyOpen?: boolean
  children: ReactNode
}) {
  return <details className="studio-subject-disclosure" open={initiallyOpen}>
    <summary>
      <PackageOpen size={16} aria-hidden="true" />
      <span>一致性主体</span>
      <small>{status}</small>
      <ChevronDown size={16} aria-hidden="true" />
    </summary>
    {children}
  </details>
}
