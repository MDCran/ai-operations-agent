import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { api, write } from '../services/api'
import type { Entity, Organization, Page } from '../types'
import { Badge, ErrorState, Header, Loading, text } from '../components/shared'
import { Button } from '../components/ui/button'
import { Modal } from '../components/ui/dialog'

function clock(minutes: number) {
  return `${String(Math.floor((minutes % 1440) / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`
}
function minutes(value: FormDataEntryValue | null, closing = false) {
  const [hour, minute] = String(value).split(':').map(Number)
  const result = hour * 60 + minute
  return closing && result === 0 ? 1440 : result
}

export function Settings({
  section,
  manage,
}: {
  section: 'organization' | 'team' | 'ai-settings'
  manage: boolean
}) {
  const client = useQueryClient()
  const [error, setError] = useState<unknown>()
  const [notice, setNotice] = useState('')
  const [open, setOpen] = useState(false)
  const query = useQuery({
    queryKey: [section],
    queryFn: () =>
      api<
        Organization & {
          items?: Entity[]
          provider?: string
          model?: string
          embedding_model?: string
          tracing_enabled?: boolean
          configuration?: string
        }
      >(`/${section}`),
  })
  const hours = useQuery({
    queryKey: ['business-hours'],
    queryFn: () => api<Page>('/business-hours'),
    enabled: section === 'organization',
  })
  const appointmentTypes = useQuery({
    queryKey: ['appointment-types'],
    queryFn: () => api<Page>('/appointment-types'),
    enabled: section === 'organization',
  })
  function saved() {
    setNotice('Changes saved.')
    void client.invalidateQueries()
  }
  const title =
    section === 'organization'
      ? 'Organization'
      : section === 'team'
        ? 'Team & roles'
        : 'AI settings'
  if (query.isPending) return <Loading />
  if (query.error) return <ErrorState error={query.error} />
  return (
    <>
      <Header
        eyebrow="ADMINISTRATION"
        title={title}
        description={
          section === 'organization'
            ? 'Business context, scheduling hours and approval policy.'
            : section === 'team'
              ? 'Manage access to your organization.'
              : 'The active model provider and runtime configuration.'
        }
        action={
          section === 'team' &&
          manage && (
            <Button onClick={() => setOpen(true)}>
              <Plus size={16} /> Add teammate
            </Button>
          )
        }
      />
      {notice && (
        <div className="notice" role="status">
          {notice}
        </div>
      )}
      {error !== undefined && <ErrorState error={error} />}
      {section === 'organization' && (
        <>
          <form
            className="card settings-form"
            key={query.data.updated_at}
            onSubmit={async (e) => {
              e.preventDefault()
              const values = new FormData(e.currentTarget)
              try {
                await write(
                  '/organization',
                  {
                    name: values.get('name'),
                    timezone: values.get('timezone'),
                    business_information: values.get('business_information'),
                    approval_tools: String(values.get('approval_tools') || '')
                      .split(',')
                      .map((v) => v.trim())
                      .filter(Boolean),
                  },
                  'PATCH',
                )
                saved()
              } catch (err) {
                setError(err)
              }
            }}
          >
            <h2>Business profile</h2>
            <label>
              Name
              <input
                name="name"
                required
                defaultValue={query.data.name}
                disabled={!manage}
              />
            </label>
            <label>
              IANA time zone
              <input
                name="timezone"
                required
                defaultValue={query.data.timezone}
                disabled={!manage}
              />
            </label>
            <label>
              Business information
              <textarea
                name="business_information"
                rows={4}
                defaultValue={query.data.business_information}
                disabled={!manage}
              />
            </label>
            <label>
              Additional approval tools (comma separated)
              <input
                name="approval_tools"
                defaultValue={query.data.approval_tools.join(', ')}
                disabled={!manage}
              />
            </label>
            <p className="muted">
              Appointment cancellation, customer deletion and sensitive CRM
              changes always require approval.
            </p>
            {manage && <Button>Save profile</Button>}
          </form>
          <form
            className="card settings-form"
            key={hours.data?.items.map((h) => h.updated_at).join()}
            onSubmit={async (e) => {
              e.preventDefault()
              const values = new FormData(e.currentTarget)
              const rows = Array.from({ length: 7 }, (_, weekday) => ({
                weekday,
                open_minute: minutes(values.get(`open-${weekday}`)),
                close_minute: minutes(values.get(`close-${weekday}`), true),
              })).filter((h) => values.has(`enabled-${h.weekday}`))
              try {
                await write('/business-hours', { hours: rows }, 'PUT')
                saved()
              } catch (err) {
                setError(err)
              }
            }}
          >
            <h2>Business hours</h2>
            <p>
              All times use {query.data.timezone}. Unchecked days are closed; a
              closing time of midnight means the end of that day.
            </p>
            {Array.from({ length: 7 }, (_, day) => {
              const row = hours.data?.items.find((h) => h.weekday === day)
              return (
                <div className="hours-row" key={day}>
                  <label>
                    <input
                      type="checkbox"
                      name={`enabled-${day}`}
                      defaultChecked={!!row}
                      disabled={!manage}
                    />
                    {
                      [
                        'Monday',
                        'Tuesday',
                        'Wednesday',
                        'Thursday',
                        'Friday',
                        'Saturday',
                        'Sunday',
                      ][day]
                    }
                  </label>
                  <input
                    aria-label={`Opening time ${day}`}
                    type="time"
                    name={`open-${day}`}
                    defaultValue={clock(Number(row?.open_minute ?? 540))}
                    disabled={!manage}
                  />
                  <span>to</span>
                  <input
                    aria-label={`Closing time ${day}`}
                    type="time"
                    name={`close-${day}`}
                    defaultValue={clock(Number(row?.close_minute ?? 1020))}
                    disabled={!manage}
                  />
                </div>
              )
            })}
            {manage && <Button>Save business hours</Button>}
          </form>
          <section className="card settings-form">
            <h2>Appointment types</h2>
            <p>Set the names and durations used by availability checks and bookings.</p>
            {appointmentTypes.data?.items.map((item) => (
              <form className="appointment-type-row" key={item.id} onSubmit={async (event) => {
                event.preventDefault()
                const form = new FormData(event.currentTarget)
                try {
                  await write(`/appointment-types/${item.id}`, { name: form.get('name'), duration_minutes: Number(form.get('duration_minutes')) }, 'PATCH')
                  saved()
                } catch (err) { setError(err) }
              }}>
                <label>Name<input name="name" required maxLength={100} defaultValue={String(item.name)} disabled={!manage} /></label>
                <label>Duration in minutes<input name="duration_minutes" type="number" min={15} max={240} step={15} required defaultValue={Number(item.duration_minutes)} disabled={!manage} /></label>
                {manage && <Button variant="outline">Save type</Button>}
              </form>
            ))}
            {manage && <form className="appointment-type-row" onSubmit={async (event) => {
              event.preventDefault()
              const form = new FormData(event.currentTarget)
              try {
                await write('/appointment-types', { name: form.get('name'), duration_minutes: Number(form.get('duration_minutes')) })
                event.currentTarget.reset()
                saved()
              } catch (err) { setError(err) }
            }}>
              <label>New type<input name="name" required maxLength={100} placeholder="Follow-up" /></label>
              <label>Duration in minutes<input name="duration_minutes" type="number" min={15} max={240} step={15} required defaultValue={30} /></label>
              <Button>Add appointment type</Button>
            </form>}
          </section>
        </>
      )}
      {section === 'team' && (
        <div className="card table-wrap">
          <table>
            <thead>
              <tr>
                <th>Teammate</th>
                <th>Email</th>
                <th>Role</th>
                <th>Manage role</th>
              </tr>
            </thead>
            <tbody>
              {query.data.items?.map((member) => (
                <tr key={member.id}>
                  <td>{text(member.name)}</td>
                  <td>{text(member.email)}</td>
                  <td>
                    <Badge>{text(member.role)}</Badge>
                  </td>
                  <td>
                    {manage && member.role !== 'owner' && (
                      <select
                        aria-label={`Role for ${text(member.name)}`}
                        value={text(member.role)}
                        onChange={(e) =>
                          void write(
                            `/team/${member.id}`,
                            { role: e.target.value },
                            'PATCH',
                          )
                            .then(saved)
                            .catch(setError)
                        }
                      >
                        {['admin', 'agent', 'viewer'].map((role) => (
                          <option key={role}>{role}</option>
                        ))}
                      </select>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {section === 'ai-settings' && (
        <section className="card settings-form">
          <h2>Active configuration</h2>
          <dl className="config-list">
            {['provider', 'model', 'embedding_model', 'tracing_enabled'].map(
              (key) => (
                <div key={key}>
                  <dt>{key.replace(/_/g, ' ')}</dt>
                  <dd>{text(query.data[key])}</dd>
                </div>
              ),
            )}
          </dl>
          <p>{query.data.configuration}</p>
          <p className="muted">
            Demo mode uses deterministic commands and lexical search. OpenAI
            mode needs a server-side API key. Keys are never exposed in this
            dashboard.
          </p>
        </section>
      )}
      <Modal
        open={open}
        onOpenChange={setOpen}
        title="Add teammate"
        description="Create a new account in this organization. Share its initial password through your own secure channel."
      >
        <form
          className="record-form"
          onSubmit={async (e) => {
            e.preventDefault()
            const form = new FormData(e.currentTarget)
            try {
              await write('/team', Object.fromEntries(form.entries()))
              setOpen(false)
              saved()
            } catch (err) {
              setError(err)
            }
          }}
        >
          <label>
            Name
            <input name="name" required />
          </label>
          <label>
            Email
            <input name="email" type="email" required />
          </label>
          <label>
            Initial password
            <input
              name="password"
              type="password"
              minLength={12}
              required
              autoComplete="new-password"
            />
          </label>
          <label>
            Role
            <select name="role">
              <option value="agent">Agent</option>
              <option value="viewer">Viewer</option>
              <option value="admin">Admin</option>
            </select>
          </label>
          <Button>Create account</Button>
        </form>
      </Modal>
    </>
  )
}
