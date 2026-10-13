import { LoaderCircle, SearchX } from 'lucide-react'
import type { ReactNode } from 'react'
import { Button } from './ui/button'

export function Header({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string
  title: string
  description: string
  action?: ReactNode
}) {
  return (
    <div className="page-header">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action}
    </div>
  )
}
export function Empty({
  title = 'Nothing here yet',
  children,
}: {
  title?: string
  children?: ReactNode
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <SearchX size={25} />
      </div>
      <h3>{title}</h3>
      <p>{children || 'Create your first record to get started.'}</p>
    </div>
  )
}
export function Loading() {
  return (
    <div className="loading" role="status">
      <LoaderCircle className="spin" size={21} /> Loading your workspace…
    </div>
  )
}
export function ErrorState({
  error,
  retry,
}: {
  error: unknown
  retry?: () => void
}) {
  return (
    <div className="error" role="alert">
      {error instanceof Error ? error.message : 'Something went wrong.'}
      {retry && (
        <Button variant="outline" onClick={retry}>
          Try again
        </Button>
      )}
    </div>
  )
}
export function Badge({ children }: { children: ReactNode }) {
  const value = String(children)
  return (
    <span className={`badge badge-${value.replace(/ /g, '_')}`}>
      {value.replace(/_/g, ' ')}
    </span>
  )
}
export function formatDate(value: unknown) {
  return value
    ? new Date(String(value)).toLocaleString(undefined, {
        dateStyle: 'medium',
        timeStyle: 'short',
      })
    : '—'
}
export function text(value: unknown): string {
  return value === null || value === undefined
    ? '—'
    : Array.isArray(value)
      ? value.join(', ')
      : typeof value === 'object'
        ? JSON.stringify(value)
        : String(value)
}
