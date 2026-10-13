import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  Users,
  LifeBuoy,
  CalendarDays,
  ShieldCheck,
  Activity,
  Workflow,
} from 'lucide-react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api } from '../services/api'
import type { Summary } from '../types'
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

export function Dashboard({ analytics = false }: { analytics?: boolean }) {
  const query = useQuery({
    queryKey: ['summary'],
    queryFn: () => api<Summary>('/dashboard/summary'),
    refetchInterval: 30000,
  })
  if (query.isPending) return <Loading />
  if (query.error)
    return <ErrorState error={query.error} retry={() => void query.refetch()} />
  const data = query.data
  const metrics = analytics
    ? [
        {
          title: 'Workflow runs',
          value: data.runs,
          Icon: Workflow,
          detail: `${data.failed_runs} failed runs`,
        },
        {
          title: 'Success rate',
          value: data.success_rate === null ? '—' : `${data.success_rate}%`,
          Icon: ShieldCheck,
          detail: 'Successful / all recorded runs',
        },
        {
          title: 'Tokens used',
          value: data.input_tokens + data.output_tokens,
          Icon: Activity,
          detail: `${data.input_tokens} input · ${data.output_tokens} output`,
        },
        {
          title: 'Estimated cost',
          value:
            data.estimated_cost === null
              ? '—'
              : `$${data.estimated_cost.toFixed(4)}`,
          Icon: CalendarDays,
          detail:
            data.estimated_cost === null
              ? 'Pricing has not been configured'
              : 'Based on configured token pricing',
        },
      ]
    : [
        {
          title: 'Total customers',
          value: data.customers,
          Icon: Users,
          detail: 'Contacts in your organization',
        },
        {
          title: 'Open tickets',
          value: data.open_tickets,
          Icon: LifeBuoy,
          detail: 'Open, in progress and pending',
        },
        {
          title: 'Appointments',
          value: data.appointments_this_week,
          Icon: CalendarDays,
          detail: 'Scheduled for this business week',
        },
        {
          title: 'Pending approvals',
          value: data.pending_approvals,
          Icon: ShieldCheck,
          detail: 'Waiting for a human decision',
        },
      ]
  return (
    <>
      <Header
        eyebrow="WORKSPACE SUMMARY"
        title={analytics ? 'Workflow analytics' : 'Today at a glance'}
        description={
          analytics
            ? 'Run volume, outcomes, and usage across your workflows.'
            : 'Customers, support, appointments, and the work moving between them.'
        }
        action={
          <Button asChild>
            <Link to="/playground">
              <Workflow size={17} /> Start a workflow
            </Link>
          </Button>
        }
      />
      <div className="metric-grid">
        {metrics.map(({ title, value, Icon, detail }) => (
          <div className="card metric" key={title}>
            <div className="metric-label">
              {title}
              <Icon size={18} />
            </div>
            <strong>{value}</strong>
            <small>{detail}</small>
          </div>
        ))}
      </div>
      <div className="dashboard-grid">
        <section className="card">
          <div className="section-title">
            <div>
              <h2>Workflow activity</h2>
              <p>Runs recorded over the last 14 days</p>
            </div>
            <Badge>{`${data.runs} total`}</Badge>
          </div>
          {data.run_trends.length ? (
            <div className="chart">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={data.run_trends}>
                  <CartesianGrid
                    stroke="var(--border)"
                    strokeDasharray="3 3"
                    vertical={false}
                  />
                  <XAxis
                    dataKey="date"
                    tickFormatter={(v) => String(v).slice(5)}
                    axisLine={{ stroke: 'var(--border)' }}
                    tick={{ fill: 'var(--muted)' }}
                  />
                  <YAxis
                    allowDecimals={false}
                    axisLine={{ stroke: 'var(--border)' }}
                    tick={{ fill: 'var(--muted)' }}
                  />
                  <Tooltip
                    contentStyle={{
                      background: 'var(--surface)',
                      border: '1px solid var(--border)',
                      borderRadius: 5,
                      color: 'var(--text)',
                    }}
                    labelStyle={{ color: 'var(--text)' }}
                    itemStyle={{ color: 'var(--accent)' }}
                  />
                  <Area
                    type="monotone"
                    dataKey="runs"
                    stroke="var(--accent)"
                    fill="var(--accent)"
                    fillOpacity={0.12}
                    strokeWidth={2}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <Empty title="Your workflow history starts here">
              Run a workflow in the studio to see activity over time.
            </Empty>
          )}
        </section>
        <section className="card">
          <div className="section-title">
            <div>
              <h2>Support queue</h2>
              <p>Tickets by current status</p>
            </div>
            <LifeBuoy size={20} />
          </div>
          {data.ticket_distribution.length ? (
            <div className="distribution">
              {data.ticket_distribution.map((t) => (
                <div key={t.status}>
                  <Badge>{t.status}</Badge>
                  <strong>{t.count}</strong>
                </div>
              ))}
            </div>
          ) : (
            <Empty title="A clear support queue">
              Your tickets will appear here when created.
            </Empty>
          )}
          <Link className="card-link" to="/tickets">
            View support tickets <ArrowRight size={16} />
          </Link>
        </section>
      </div>
      <section className="card">
        <div className="section-title">
          <div>
            <h2>{analytics ? 'Tool usage' : 'Recent workflows'}</h2>
            <p>
              {analytics
                ? `Average recorded execution: ${data.average_latency_ms} ms`
                : 'Latest handoffs, approvals, and completed work'}
            </p>
          </div>
          <Link to="/runs" className="text-link">
            View all runs <ArrowRight size={15} />
          </Link>
        </div>
        {analytics ? (
          data.tool_counts.length ? (
            <div className="distribution">
              {data.tool_counts.map((t) => (
                <div key={t.tool}>
                  <code>{t.tool}</code>
                  <strong>{t.count}</strong>
                </div>
              ))}
            </div>
          ) : (
            <Empty title="No tool calls yet" />
          )
        ) : data.recent_activity.length ? (
          <div className="activity-list">
            {data.recent_activity.map((run) => (
              <Link to={`/runs/${run.id}`} key={run.id}>
                <div className="activity-icon">
                  <Workflow size={19} />
                </div>
                <div>
                  <strong>{text(run.agent)} workflow</strong>
                  <small>
                    {formatDate(run.created_at)} · {text(run.provider)}
                  </small>
                </div>
                <Badge>{text(run.status)}</Badge>
                <ArrowRight size={16} />
              </Link>
            ))}
          </div>
        ) : (
          <Empty title="Nothing in motion yet">
            Ask a question, open a ticket or manage an appointment.
          </Empty>
        )}
      </section>
    </>
  )
}
