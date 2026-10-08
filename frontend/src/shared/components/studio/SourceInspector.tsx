import { X } from 'lucide-react'
import { useId, useState } from 'react'
import { ImagePreview } from '../Media'
import { IconButton } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { CreativeCanvas } from './CreativeCanvas'

export function SourceInspector({ file, label, onClose }: { file: File; label: string; onClose: () => void }) {
  const titleId = useId()
  const [expanded, setExpanded] = useState(false)
  return <>
    <Modal className="modal-backdrop" labelledBy={titleId} onClose={onClose}>
      <section className="studio-source-inspector">
        <header><h2 id={titleId}>{label}：{file.name}</h2><IconButton label="关闭素材检查" onClick={onClose}><X size={18} /></IconButton></header>
        <CreativeCanvas file={file} name={file.name} onPreview={() => setExpanded(true)} />
      </section>
    </Modal>
    {expanded ? <ImagePreview file={file} label={label} onClose={() => setExpanded(false)} /> : null}
  </>
}
