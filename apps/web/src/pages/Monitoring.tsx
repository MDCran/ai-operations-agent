import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, ArrowRight, CheckCircle2, RotateCw } from 'lucide-react'
import { api, write } from '../services/api'
import type { Entity, Page } from '../types'
import {
  Badge,
  Empty,
  ErrorState,
  formatDate,
  Header,
  Loading,
  text,
} from '../components/shared'
import { Button } from '../components/ui/button'

export function Monitoring({
  audit = false,
  writable,
}: {
  audit?: boolean
  writable: boolean
}) {
  const { id } = useParams()
  const client = useQueryClient()
  const [error, setError] = useState<unknown>()
  const [offset, setOffset] = useState(0)
  const query = useQuery({
    queryKey: [audit ? 'audit' : 'runs', id, offset],
    queryFn: () =>
      api<Page>(`${audit ? '/audit-logs' : '/agents/runs'}?offset=${offset}`),
    enabled: !id,
    refetchInterval: 10000,
  })
  const detail = useQuery({
    queryKey: ['run', id],
    queryFn: () =>
      api<{
        run: Entity
        steps: Entity[]
        tools: Entity[]
        approvals: Entity[]
      }>(`/agents/runs/${id}`),
    enabled: !!id,
    refetchInterval: 5000,
  })
  if (id)
    return (
      <>
        <Link to="/runs" className="text-link">
          <ArrowLeft size={16} /> Back to runs
        </Link>
        <Header
          eyebrow="EXECUTION INSPECTOR"
          title="Workflow detail"
          description="The recorded handoffs, tools and outcome of this run."
        />
        {detail.isPending ? (
          <Loading />
        ) : detail.error ? (
          <ErrorState error={detail.error} />
        ) : (
          <>
            <div className="card run-summary">
              <div>
                <h2>{text(detail.data.run.agent)} agent</h2>
                <p>{id}</p>
              </div>
              <Badge>{text(detail.data.run.status)}</Badge>
              <span>{text(detail.data.run.duration_ms)} ms</span>
              <span>
                {text(detail.data.run.input_tokens)} input /{' '}
                {text(detail.data.run.output_tokens)} output tokens
              </span>
              {detail.data.run.status === 'failed' && writable && (
                <Button
                  variant="outline"
                  onClick={() =>
                    void write(`/agents/runs/${id}/retry`, {})
                      .then(() => client.invalidateQueries())
                      .catch(setError)
                  }
                >
                  <RotateCw size={16} /> Retry workflow
                </Button>
              )}
            </div>
            <div className="dashboard-grid">
              <section className="card">
                <div className="section-title">
                  <h2>Node execution</h2>
                </div>
                {detail.data.steps.map((step) => (
                  <div className="timeline-step" key={step.id}>
                    <CheckCircle2 size={18} />
                    <div>
                      <strong>{text(step.node).replace(/_/g, ' ')}</strong>
                      <small>{formatDate(step.created_at)}</small>
                    </div>
                  </div>
                ))}
                {!detail.data.steps.length && (
                  <Empty title="No completed nodes" />
                )}
              </section>
              <section className="card">
                <div className="section-title">
                  <h2>Tool calls</h2>
                </div>
                {detail.data.tools.map((tool) => (
                  <div className="tool-row" key={tool.id}>
                    <code>{text(tool.tool)}</code>
                    <Badge>{text(tool.status)}</Badge>
                    <small>
                      {text(tool.duration_ms)} ms · {text(tool.error_code)}
                    </small>
                  </div>
                ))}
                {!detail.data.tools.length && (
                  <Empty title="No tool calls recorded" />
                )}
              </section>
            </div>
            <section className="card detail-outcome">
              <h2>Outcome</h2>
              {!!detail.data.run.error_code && (
                <div className="error">
                  Error: {text(detail.data.run.error_code)}
                </div>
              )}
              <pre>{JSON.stringify(detail.data.run.outcome, null, 2)}</pre>
              {detail.data.approvals.map((approval) => (
                <Link key={approval.id} className="text-link" to="/approvals">
                  Approval: {text(approval.action)} · {text(approval.status)}
                </Link>
              ))}
            </section>
            {error !== undefined && <ErrorState error={error} />}
          </>
        )}
      </>
    )
  return (
    <>
      <Header
        eyebrow={audit ? 'ADMINISTRATION' : 'MONITORING'}
        title={audit ? 'Audit logs' : 'Runs & workflows'}
        description={
          audit
            ? 'An organization-scoped record of changes, actors and affected resources.'
            : 'Inspect every execution, handoff and tool call.'
        }
      />
      <div className="card">
        {query.isPending ? (
          <Loading />
        ) : query.error ? (
          <ErrorState error={query.error} />
        ) : !query.data.items.length ? (
          <Empty
            title={audit ? 'No changes recorded yet' : 'No workflow runs yet'}
          />
        ) : (
          <>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>{audit ? 'Action' : 'Agent'}</th>
                    <th>{audit ? 'Resource' : 'Status'}</th>
                    <th>{audit ? 'Actor' : 'Duration'}</th>
                    <th>Time</th>
                    <th>{audit ? 'Fields changed' : 'Details'}</th>
                  </tr>
                </thead>
                <tbody>
                  {query.data.items.map((row) => (
                    <tr key={row.id}>
                      <td>
                        <strong>{text(audit ? row.action : row.agent)}</strong>
                      </td>
                      <td>
                        {audit ? (
                          <code>{text(row.resource_id).slice(0, 8)}</code>
                        ) : (
                          <Badge>{text(row.status)}</Badge>
                        )}
                      </td>
                      <td>
                        {audit
                          ? text(row.actor_id).slice(0, 8)
                          : `${text(row.duration_ms)} ms`}
                      </td>
                      <td>{formatDate(row.created_at)}</td>
                      <td>
                        {audit ? (
                          text(row.changed_fields)
                        ) : (
                          <Link className="text-link" to={`/runs/${row.id}`}>
                            Inspect <ArrowRight size={15} />
                          </Link>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="pagination">
              <small>{query.data.total} records</small>
              <div>
                <Button
                  variant="outline"
                  disabled={!offset}
                  onClick={() => setOffset(offset - 25)}
                >
                  Previous
                </Button>
                <Button
                  variant="outline"
                  disabled={offset + 25 >= query.data.total}
                  onClick={() => setOffset(offset + 25)}
                >
                  Next
                </Button>
              </div>
            </div>
          </>
        )}
      </div>
    </>
  )
}
