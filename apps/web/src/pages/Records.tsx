import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import {
  ChevronLeft,
  ChevronRight,
  Plus,
  Search,
  Pencil,
  ArrowRight,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { Link } from 'react-router-dom'
import { api, write } from '../services/api'
import type { Customer, Entity, Page } from '../types'
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
import { Modal } from '../components/ui/dialog'

type Kind = 'customers' | 'tickets' | 'appointments' | 'tasks'
type Field = {
  key: string
  label: string
  type?: string
  options?: string[]
  required?: boolean
}
const definitions: Record<
  Kind,
  {
    title: string
    description: string
    columns: [string, string][]
    statuses: string[]
    fields: Field[]
  }
> = {
  customers: {
    title: 'Customers',
    description: 'The people and companies behind your operations.',
    columns: [
      ['name', 'Customer'],
      ['email', 'Email'],
      ['company', 'Company'],
      ['status', 'Status'],
    ],
    statuses: ['active', 'lead', 'inactive'],
    fields: [
      { key: 'first_name', label: 'First name', required: true },
      { key: 'last_name', label: 'Last name' },
      { key: 'email', label: 'Email', type: 'email', required: true },
      { key: 'phone', label: 'Phone' },
      { key: 'company', label: 'Company' },
      {
        key: 'status',
        label: 'Status',
        options: ['active', 'lead', 'inactive'],
      },
      { key: 'tags', label: 'Tags (comma separated)' },
      { key: 'notes', label: 'Notes', type: 'textarea' },
    ],
  },
  tickets: {
    title: 'Support tickets',
    description: 'Track questions, resolve issues and keep customers moving.',
    columns: [
      ['title', 'Ticket'],
      ['priority', 'Priority'],
      ['status', 'Status'],
      ['category', 'Category'],
    ],
    statuses: ['open', 'in_progress', 'pending', 'resolved', 'closed'],
    fields: [
      { key: 'title', label: 'Title', required: true },
      { key: 'description', label: 'Description', type: 'textarea' },
      { key: 'customer_id', label: 'Customer', type: 'customer' },
      {
        key: 'priority',
        label: 'Priority',
        options: ['low', 'medium', 'high', 'urgent'],
      },
      { key: 'category', label: 'Category' },
    ],
  },
  appointments: {
    title: 'Appointments',
    description:
      'Book available business hours. All bookings are checked for conflicts.',
    columns: [
      ['title', 'Appointment'],
      ['starts_at', 'Starts at'],
      ['ends_at', 'Ends at'],
      ['status', 'Status'],
    ],
    statuses: ['confirmed', 'completed', 'cancelled'],
    fields: [
      { key: 'title', label: 'Title', required: true },
      {
        key: 'customer_id',
        label: 'Customer',
        type: 'customer',
        required: true,
      },
      {
        key: 'appointment_type_id',
        label: 'Appointment type',
        type: 'appointment-type',
        required: true,
      },
      { key: 'date', label: 'Business date', type: 'date', required: true },
    ],
  },
  tasks: {
    title: 'Tasks',
    description: 'Turn operational decisions into a focused action list.',
    columns: [
      ['title', 'Task'],
      ['status', 'Status'],
      ['due_at', 'Due date'],
      ['created_at', 'Created'],
    ],
    statuses: ['todo', 'in_progress', 'done'],
    fields: [
      { key: 'title', label: 'Title', required: true },
      { key: 'description', label: 'Description', type: 'textarea' },
      { key: 'due_at', label: 'Due date', type: 'datetime-local' },
    ],
  },
}

const formSchema = z.record(z.string(), z.string())
function Editor({
  kind,
  current,
  onSaved,
  onClose,
}: {
  kind: Kind
  current?: Entity
  onSaved: (message: string) => void
  onClose: () => void
}) {
  const [error, setError] = useState<unknown>()
  const [slots, setSlots] = useState<{ starts_at: string; ends_at: string }[]>(
    [],
  )
  const [zone, setZone] = useState('')
  const [slot, setSlot] = useState('')
  const [checking, setChecking] = useState(false)
  const defaults: Record<string, string> = {}
  for (const field of definitions[kind].fields) {
    const value = current?.[field.key]
    defaults[field.key] = Array.isArray(value)
      ? value.join(', ')
      : value === null || value === undefined
        ? field.options?.[0] || ''
        : String(value)
    if (field.type === 'datetime-local' && value) {
      const date = new Date(String(value))
      defaults[field.key] = new Date(
        date.getTime() - date.getTimezoneOffset() * 60000,
      )
        .toISOString()
        .slice(0, 16)
    }
  }
  if (current && kind === 'tickets') {
    defaults.status = String(current.status)
    defaults.assigned_user_id = String(current.assigned_user_id || '')
  }
  if (current && kind === 'tasks') defaults.status = String(current.status)
  const {
    register,
    handleSubmit,
    watch,
    formState: { isSubmitting },
  } = useForm<Record<string, string>>({
    resolver: zodResolver(formSchema),
    defaultValues: defaults,
  })
  const customers = useQuery({
    queryKey: ['customer-options'],
    queryFn: () => api<Page<Customer>>('/customers?limit=100'),
    enabled: kind === 'tickets' || kind === 'appointments',
  })
  const types = useQuery({
    queryKey: ['appointment-types'],
    queryFn: () => api<Page>('/appointment-types'),
    enabled: kind === 'appointments',
  })
  const team = useQuery({
    queryKey: ['team-options'],
    queryFn: () => api<{ items: { user_id: string; name: string }[] }>('/team'),
    enabled: kind === 'tickets' && !!current,
  })
  const fields =
    current && kind === 'appointments'
      ? [
          {
            key: 'date',
            label: 'New business date',
            type: 'date',
            required: true,
          },
        ]
      : definitions[kind].fields.filter(
          (f) => !(current && f.key === 'customer_id'),
        )
  const date = watch('date')
  const typeId = current
    ? String(current.appointment_type_id)
    : watch('appointment_type_id')
  useEffect(() => {
    setSlot('')
    setSlots([])
    setZone('')
  }, [date, typeId])
  return (
    <form
      className="record-form"
      onSubmit={handleSubmit(async (values) => {
        try {
          setError(undefined)
          let body: Record<string, unknown> = { ...values }
          if (kind === 'customers')
            body.tags = values.tags
              .split(',')
              .map((t) => t.trim())
              .filter(Boolean)
          if (kind === 'tickets' && !current && !values.customer_id)
            body.customer_id = null
          if (kind === 'tickets' && current)
            body.assigned_user_id = values.assigned_user_id || null
          if (kind === 'tasks')
            body.due_at = values.due_at
              ? new Date(values.due_at).toISOString()
              : null
          if (kind === 'appointments') {
            if (!slot) throw new Error('Check availability and select a slot.')
            body = current
              ? { starts_at: slot }
              : {
                  title: values.title,
                  customer_id: values.customer_id,
                  appointment_type_id: values.appointment_type_id,
                  starts_at: slot,
                }
          }
          if (current && kind !== 'appointments')
            body = Object.fromEntries(
              Object.entries(body).filter(
                ([key, value]) =>
                  JSON.stringify(value) !==
                  JSON.stringify(
                    current[key] ??
                      (key === 'assigned_user_id' || key === 'due_at'
                        ? null
                        : ''),
                  ),
              ),
            )
          if (current && !Object.keys(body).length) {
            onClose()
            return
          }
          const result = await write<{ status?: string }>(
            `/${kind}${current ? `/${current.id}` : ''}`,
            body,
            current ? 'PATCH' : 'POST',
          )
          onSaved(
            result.status === 'pending_approval'
              ? 'Change submitted for approval. Review it in Approvals.'
              : 'Record saved successfully.',
          )
        } catch (e) {
          setError(e)
        }
      })}
    >
      <div className="form-grid">
        {fields.map((field) => (
          <label
            className={field.type === 'textarea' ? 'full-width' : ''}
            key={field.key}
          >
            {field.label}
            {field.type === 'textarea' ? (
              <textarea rows={4} {...register(field.key)} />
            ) : field.options ? (
              <select {...register(field.key)}>
                {field.options.map((o) => (
                  <option key={o} value={o}>
                    {o.replace(/_/g, ' ')}
                  </option>
                ))}
              </select>
            ) : field.type === 'customer' ||
              field.type === 'appointment-type' ? (
              <select required={field.required} {...register(field.key)}>
                <option value="">Select…</option>
                {(field.type === 'customer'
                  ? customers.data?.items
                  : types.data?.items
                )?.map((item) => (
                  <option key={item.id} value={item.id}>
                    {field.type === 'customer'
                      ? `${text(item.first_name)} ${text(item.last_name)}`
                      : text(item.name)}
                  </option>
                ))}
              </select>
            ) : (
              <input
                type={field.type || 'text'}
                required={field.required}
                maxLength={field.key === 'title' ? 200 : undefined}
                {...register(field.key)}
              />
            )}
          </label>
        ))}
        {current && (kind === 'tickets' || kind === 'tasks') && (
          <label>
            Status
            <select {...register('status')}>
              {definitions[kind].statuses.map((status) => (
                <option key={status} value={status}>
                  {status.replace(/_/g, ' ')}
                </option>
              ))}
            </select>
          </label>
        )}
        {current && kind === 'tickets' && (
          <label>
            Assigned to
            <select {...register('assigned_user_id')}>
              <option value="">Unassigned</option>
              {team.data?.items.map((user) => (
                <option key={user.user_id} value={user.user_id}>
                  {user.name}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      {kind === 'appointments' && (
        <div className="slot-picker">
          <Button
            type="button"
            variant="outline"
            disabled={!date || !typeId || checking}
            onClick={async () => {
              setChecking(true)
              setSlot('')
              setError(undefined)
              try {
                const result = await write<{
                  slots: typeof slots
                  timezone: string
                }>('/appointments/availability', {
                  date,
                  appointment_type_id: typeId,
                })
                setSlots(result.slots)
                setZone(result.timezone)
              } catch (e) {
                setError(e)
              } finally {
                setChecking(false)
              }
            }}
          >
            {checking ? 'Checking…' : 'Check availability'}
          </Button>
          {zone && (
            <>
              <p>
                Times in {zone}. Availability is checked again when booking.
              </p>
              {slots.length ? (
                <div className="slots">
                  {slots.map((s) => (
                    <button
                      type="button"
                      className={slot === s.starts_at ? 'selected' : ''}
                      key={s.starts_at}
                      onClick={() => setSlot(s.starts_at)}
                    >
                      {new Date(s.starts_at).toLocaleTimeString(undefined, {
                        timeZone: zone,
                        hour: 'numeric',
                        minute: '2-digit',
                      })}
                    </button>
                  ))}
                </div>
              ) : (
                <p>No available slots on this date.</p>
              )}
            </>
          )}
        </div>
      )}
      {customers.error && <ErrorState error={customers.error} />}
      {types.error && <ErrorState error={types.error} />}
      {error !== undefined && <ErrorState error={error} />}
      <div className="form-actions">
        <Button type="button" variant="outline" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting
            ? 'Saving…'
            : current
              ? 'Save changes'
              : 'Create record'}
        </Button>
      </div>
    </form>
  )
}

function Detail({
  kind,
  item,
  writable,
  close,
  onSaved,
}: {
  kind: Kind
  item: Entity
  writable: boolean
  close: () => void
  onSaved: (message: string) => void
}) {
  const [comment, setComment] = useState('')
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>()
  const query = useQuery({
    queryKey: ['detail', kind, item.id],
    queryFn: () =>
      api<Record<string, Entity | Entity[]>>(`/${kind}/${item.id}`),
    enabled: kind === 'customers' || kind === 'tickets',
  })
  return (
    <div className="record-detail">
      <dl>
        {Object.entries(item)
          .filter(
            ([key]) => !['organization_id', 'version', 'id'].includes(key),
          )
          .map(([key, value]) => (
            <div key={key}>
              <dt>{key.replace(/_/g, ' ')}</dt>
              <dd>{key.endsWith('_at') ? formatDate(value) : text(value)}</dd>
            </div>
          ))}
      </dl>
      {kind === 'customers' && (
        <>
          {['tickets', 'appointments'].map((key) => {
            const rows = query.data?.[key] as Entity[] | undefined
            return (
              <section key={key}>
                <h3>Related {key}</h3>
                {rows?.length ? (
                  rows.map((row) => (
                    <p key={row.id}>
                      {text(row.title)} · <Badge>{text(row.status)}</Badge>
                    </p>
                  ))
                ) : (
                  <p className="muted">No related records.</p>
                )}
              </section>
            )
          })}
          {writable && (
            <Button
              variant="destructive"
              onClick={async () => {
                try {
                  await api(`/customers/${item.id}`, { method: 'DELETE' })
                  onSaved('Deletion submitted for approval.')
                  close()
                } catch (e) {
                  setError(e)
                }
              }}
            >
              Request customer deletion
            </Button>
          )}
        </>
      )}
      {kind === 'tickets' && (
        <>
          <h3>Comments</h3>
          {(query.data?.comments as Entity[] | undefined)?.map((row) => (
            <div className="comment" key={row.id}>
              <p>{text(row.body)}</p>
              <small>{formatDate(row.created_at)}</small>
            </div>
          ))}
          {writable && (
            <>
              <form
                onSubmit={async (e) => {
                  e.preventDefault()
                  setBusy(true)
                  try {
                    await write(`/tickets/${item.id}/comments`, {
                      body: comment,
                    })
                    setComment('')
                    void query.refetch()
                  } catch (e) {
                    setError(e)
                  } finally {
                    setBusy(false)
                  }
                }}
              >
                <label>
                  Add an internal comment
                  <textarea
                    required
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                  />
                </label>
                <Button disabled={busy || !comment}>Add comment</Button>
              </form>
              <Button
                variant="outline"
                disabled={busy}
                onClick={async () => {
                  setBusy(true)
                  try {
                    const result = await write<{
                      draft: { text?: string }
                      status: string
                    }>(`/tickets/${item.id}/draft`, {})
                    if (result.status !== 'succeeded')
                      throw new Error(
                        'Draft workflow failed; inspect Agent Runs.',
                      )
                    setDraft(result.draft.text || '')
                  } catch (e) {
                    setError(e)
                  } finally {
                    setBusy(false)
                  }
                }}
              >
                Draft response from knowledge
              </Button>
              {draft && (
                <div className="prose draft">
                  <ReactMarkdown>{draft}</ReactMarkdown>
                  <small>
                    Internal draft. External sending is not configured.
                  </small>
                </div>
              )}
            </>
          )}
        </>
      )}
      {kind === 'appointments' && writable && item.status === 'confirmed' && (
        <Button
          variant="destructive"
          onClick={async () => {
            try {
              await write(`/appointments/${item.id}/cancel`, {})
              onSaved('Cancellation submitted for approval.')
              close()
            } catch (e) {
              setError(e)
            }
          }}
        >
          Request cancellation
        </Button>
      )}
      {query.error && <ErrorState error={query.error} />}
      {error !== undefined && <ErrorState error={error} />}
    </div>
  )
}

export function Records({ kind, writable }: { kind: Kind; writable: boolean }) {
  const client = useQueryClient()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [offset, setOffset] = useState(0)
  const [sort, setSort] = useState('created_at')
  const [modal, setModal] = useState<{
    type: 'create' | 'edit' | 'detail'
    item?: Entity
  } | null>(null)
  const [notice, setNotice] = useState('')
  const query = useQuery({
    queryKey: [kind, search, status, offset, sort],
    queryFn: () =>
      api<Page>(
        `/${kind}?q=${encodeURIComponent(search)}&status=${status}&offset=${offset}&sort=${sort}`,
      ),
  })
  const def = definitions[kind]
  const saved = (message: string) => {
    setNotice(message)
    setModal(null)
    void client.invalidateQueries()
  }
  return (
    <>
      <Header
        eyebrow="OPERATIONS"
        title={def.title}
        description={def.description}
        action={
          writable && (
            <Button onClick={() => setModal({ type: 'create' })}>
              <Plus size={17} /> Add{' '}
              {kind === 'customers'
                ? 'customer'
                : kind === 'tickets'
                  ? 'ticket'
                  : kind === 'tasks'
                    ? 'task'
                    : 'appointment'}
            </Button>
          )
        }
      />
      {notice && (
        <div className="notice" role="status">
          {notice}
          {notice.includes('approval') && (
            <Link to="/approvals">
              Review approvals <ArrowRight size={15} />
            </Link>
          )}
        </div>
      )}
      <div className="card">
        <div className="table-toolbar">
          <div className="search-field">
            <Search size={18} />
            <input
              aria-label={`Search ${kind}`}
              placeholder={`Search ${def.title.toLowerCase()}…`}
              value={search}
              onChange={(e) => {
                setSearch(e.target.value)
                setOffset(0)
              }}
            />
          </div>
          <select
            aria-label="Filter status"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value)
              setOffset(0)
            }}
          >
            <option value="">All statuses</option>
            {def.statuses.map((s) => (
              <option key={s} value={s}>
                {s.replace(/_/g, ' ')}
              </option>
            ))}
          </select>
          <select
            aria-label="Sort records"
            value={sort}
            onChange={(e) => setSort(e.target.value)}
          >
            <option value="created_at">Newest first</option>
            <option value="updated_at">Recently updated</option>
            <option value={kind === 'customers' ? 'first_name' : 'title'}>
              Name
            </option>
          </select>
        </div>
        {query.isPending ? (
          <Loading />
        ) : query.error ? (
          <ErrorState error={query.error} retry={() => void query.refetch()} />
        ) : query.data.items.length ? (
          <>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    {def.columns.map(([key, label]) => (
                      <th key={key}>{label}</th>
                    ))}
                    <th>Updated</th>
                    <th>
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {query.data.items.map((item) => (
                    <tr key={item.id}>
                      {def.columns.map(([key]) => (
                        <td key={key}>
                          {key === 'name' || key === 'title' ? (
                            <button
                              className="record-title"
                              onClick={() => setModal({ type: 'detail', item })}
                            >
                              {key === 'name'
                                ? `${text(item.first_name)} ${text(item.last_name)}`
                                : text(item.title)}
                              <small>{item.id.slice(0, 8)}</small>
                            </button>
                          ) : ['status', 'priority'].includes(key) ? (
                            <Badge>{text(item[key])}</Badge>
                          ) : key.endsWith('_at') ? (
                            formatDate(item[key])
                          ) : (
                            text(item[key])
                          )}
                        </td>
                      ))}
                      <td className="muted">{formatDate(item.updated_at)}</td>
                      <td>
                        {writable && (
                          <Button
                            variant="ghost"
                            aria-label={`Edit ${text(item.title || item.first_name)}`}
                            onClick={() => setModal({ type: 'edit', item })}
                          >
                            <Pencil size={16} />
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="pagination">
              <small>
                {offset + 1}–{Math.min(offset + 25, query.data.total)} of{' '}
                {query.data.total} records
              </small>
              <div>
                <Button
                  variant="outline"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - 25))}
                >
                  <ChevronLeft size={16} /> Previous
                </Button>
                <Button
                  variant="outline"
                  disabled={offset + 25 >= query.data.total}
                  onClick={() => setOffset(offset + 25)}
                >
                  Next <ChevronRight size={16} />
                </Button>
              </div>
            </div>
          </>
        ) : (
          <Empty
            title={
              search || status
                ? 'No matching records'
                : `No ${def.title.toLowerCase()} yet`
            }
          >
            {search || status
              ? 'Try another search or filter.'
              : 'Create a record here or ask an agent to help.'}
          </Empty>
        )}
      </div>
      <Modal
        open={!!modal}
        onOpenChange={(open) => {
          if (!open) setModal(null)
        }}
        title={
          modal?.type === 'detail'
            ? 'Record details'
            : `${modal?.type === 'edit' ? 'Edit' : 'Add'} ${kind.slice(0, -1)}`
        }
        description={
          kind === 'customers'
            ? 'Sensitive changes are reviewed in Approvals before they take effect.'
            : undefined
        }
      >
        {modal &&
          (modal.type === 'detail' && modal.item ? (
            <Detail
              kind={kind}
              item={modal.item}
              writable={writable}
              close={() => setModal(null)}
              onSaved={saved}
            />
          ) : (
            <Editor
              kind={kind}
              current={modal.item}
              onSaved={saved}
              onClose={() => setModal(null)}
            />
          ))}
      </Modal>
    </>
  )
}
