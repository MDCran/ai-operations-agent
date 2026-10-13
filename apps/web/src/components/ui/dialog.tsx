import * as Dialog from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import type { ReactNode } from 'react'

export function Modal({
  open,
  onOpenChange,
  title,
  description,
  children,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  title: string
  description?: string
  children: ReactNode
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal
        container={
          document.querySelector<HTMLElement>('.app-root') ?? undefined
        }
      >
        <Dialog.Overlay className="modal-overlay" />
        <Dialog.Content className="modal-content">
          <Dialog.Title>{title}</Dialog.Title>
          <Dialog.Description>
            {description || 'Review the details below.'}
          </Dialog.Description>
          <Dialog.Close className="modal-close" aria-label="Close dialog">
            <X size={20} />
          </Dialog.Close>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
