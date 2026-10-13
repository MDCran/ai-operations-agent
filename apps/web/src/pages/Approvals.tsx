import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, X, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api, write } from '../services/api'
import type { Approval, Page } from '../types'
import {
  Badge,
  Empty,
  ErrorState,
  formatDate,
  Header,
  Loading,
} from '../components/shared'
import { Button } from '../components/ui/button'
import { Modal } from '../components/ui/dialog'

export function Approvals({ canApprove }: { canApprove: boolean }) {
  const client = useQueryClient()
  const [status, setStatus] = useState('pending')
  const [error, setError] = useState<unknown>()
  const [decision, setDecision] = useState<{
    row: Approval
    action: 'approve' | 'reject'
  } | null>(null)
  const [busy, setBusy] = useState(false)
  const query = useQuery({
    queryKey: ['approvals', status],
    queryFn: () => api<Page<Approval>>(`/approvals?limit=100&status=${status}`),
    refetchInterval: 5000,
  })
  return (
    <>
      <Header
        eyebrow="HUMAN IN THE LOOP"
        title="Approvals"
        description="Review the exact proposed action before a workflow continues."
        action={<ShieldCheck size={26} />}
      />
      <div className="tabs">
        {[
          'pending',
          'approved',
          'executed',
          'rejected',
          'expired',
          'cancelled',
        ].map((s) => (
          <button
            key={s}
            className={status === s ? 'active' : ''}
            onClick={() => setStatus(s)}
          >
            {s}
          </button>
        ))}
      </div>
      {error !== undefined && <ErrorState error={error} />}
      {query.isPending ? (
        <Loading />
      ) : query.error ? (
        <ErrorState error={query.error} />
      ) : !query.data.items.length ? (
        <div className="card">
          <Empty title={`No ${status} approvals`}>
            Protected actions appear here before they execute.
          </Empty>
        </div>
      ) : (
        <div className="approval-list">
          {query.data.items.map((row) => (
            <article className="card approval-card" key={row.id}>
              <div className="section-title">
                <div>
                  <h2>{row.action.replace(/_/g, ' ')}</h2>
                  <p>{row.reason}</p>
                </div>
                <Badge>{row.status}</Badge>
              </div>
              <div className="approval-meta">
                <span>
                  Resource <code>{row.resource_id || 'New record'}</code>
                </span>
                <span>Requested {formatDate(row.created_at)}</span>
                <span>Expires {formatDate(row.expires_at)}</span>
                <span>
                  Requester <code>{row.requester_id.slice(0, 8)}</code>
                </span>
              </div>
              <h3>Proposed changes</h3>
              <pre className="payload">
                {JSON.stringify(row.payload, null, 2)}
              </pre>
              <div className="approval-footer">
                <Link to={`/runs/${row.run_id}`} className="text-link">
                  Inspect workflow
                </Link>
                {row.status === 'pending' && canApprove && (
                  <div>
                    <Button
                      variant="outline"
                      onClick={() => setDecision({ row, action: 'reject' })}
                    >
                      <X size={16} /> Reject
                    </Button>
                    <Button
                      onClick={() => setDecision({ row, action: 'approve' })}
                    >
                      <Check size={16} /> Approve action
                    </Button>
                  </div>
                )}
                {row.status === 'pending' && !canApprove && (
                  <small>Owner or admin approval required.</small>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
      <Modal
        open={!!decision}
        onOpenChange={(open) => {
          if (!open) setDecision(null)
        }}
        title={`${decision?.action === 'approve' ? 'Approve' : 'Reject'} this action?`}
        description={
          decision?.action === 'approve'
            ? 'The workflow will recheck permissions and record state, then execute the reviewed action once.'
            : 'The workflow will finish without executing the proposed change.'
        }
      >
        <pre className="payload">
          {JSON.stringify(decision?.row.payload, null, 2)}
        </pre>
        <div className="form-actions">
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => setDecision(null)}
          >
            Back
          </Button>
          <Button
            disabled={busy}
            onClick={async () => {
              if (!decision) return
              setBusy(true)
              try {
                await write(
                  `/approvals/${decision.row.id}/${decision.action}`,
                  {},
                )
                setDecision(null)
                await client.invalidateQueries()
              } catch (e) {
                setError(e)
              } finally {
                setBusy(false)
              }
            }}
          >
            {busy ? 'Recording decision…' : 'Confirm decision'}
          </Button>
        </div>
      </Modal>
    </>
  )
}
