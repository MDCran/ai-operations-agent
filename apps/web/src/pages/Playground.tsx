import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Plus,
  Send,
  FileText,
  CheckCircle2,
  Workflow,
  ArrowRight,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { Link } from 'react-router-dom'
import { api, streamChat, write } from '../services/api'
import type { Conversation, Entity, Message, Page, StreamEvent } from '../types'
import { Badge, ErrorState, Header, Loading } from '../components/shared'
import { Button } from '../components/ui/button'

export function Playground({ writable }: { writable: boolean }) {
  const client = useQueryClient()
  const [id, setId] = useState('')
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [events, setEvents] = useState<StreamEvent[]>([])
  const [error, setError] = useState<unknown>()
  const [search, setSearch] = useState('')
  const [optimistic, setOptimistic] = useState('')
  const controller = useRef<AbortController | null>(null)
  const bottom = useRef<HTMLDivElement>(null)
  const conversations = useQuery({
    queryKey: ['conversations', search],
    queryFn: () =>
      api<Page<Conversation>>(
        `/conversations?limit=100&q=${encodeURIComponent(search)}`,
      ),
  })
  const messages = useQuery({
    queryKey: ['messages', id],
    queryFn: () => api<{ messages: Message[] }>(`/conversations/${id}`),
    enabled: !!id,
    refetchInterval: busy ? false : 5000,
  })
  const settings = useQuery({
    queryKey: ['ai-settings'],
    queryFn: () => api<{ provider: string }>('/ai-settings'),
  })
  useEffect(() => () => controller.current?.abort(), [])
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [messages.data, events, optimistic])
  async function newConversation() {
    const row = await write<Entity>('/conversations', {})
    setId(row.id)
    setEvents([])
    await client.invalidateQueries({ queryKey: ['conversations'] })
    return row.id
  }
  async function send() {
    if (!input.trim() || busy) return
    const message = input.trim()
    setBusy(true)
    setError(undefined)
    setEvents([])
    setOptimistic(message)
    setInput('')
    controller.current = new AbortController()
    try {
      const conversationId = id || (await newConversation())
      await streamChat(
        {
          conversation_id: conversationId,
          message,
          request_id: crypto.randomUUID(),
        },
        (event) => {
          setEvents((previous) => [...previous, event])
          if (event.type === 'error') setError(new Error(event.data.message))
        },
        controller.current.signal,
      )
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
      setOptimistic('')
      await client.invalidateQueries()
    }
  }
  const pending = events.find((e) => e.type === 'approval')
  const runId = events.find((e) => e.type === 'run')?.data.run_id
  return (
    <>
      <Header
        eyebrow="AUTOMATION"
        title="Workflow studio"
        description="Start a conversation, hand off routine work, and review every action."
        action={
          <Badge>
            {settings.data?.provider === 'demo'
              ? 'Local demo mode'
              : 'OpenAI provider'}
          </Badge>
        }
      />
      <div className="playground">
        <aside className="conversation-sidebar">
          <Button
            variant="outline"
            disabled={!writable || busy}
            onClick={() => void newConversation().catch(setError)}
          >
            <Plus size={16} /> New conversation
          </Button>
          <input
            aria-label="Search conversations"
            placeholder="Search conversations…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <span className="eyebrow">RECENT CONVERSATIONS</span>
          {conversations.data?.items.map((row) => (
            <button
              disabled={busy}
              className={id === row.id ? 'active' : ''}
              key={row.id}
              onClick={() => {
                setId(row.id)
                setEvents([])
                setError(undefined)
              }}
            >
              {row.title}
              <small>{new Date(row.created_at).toLocaleDateString()}</small>
            </button>
          ))}
          {conversations.error && <ErrorState error={conversations.error} />}
        </aside>
        <section className="chat-panel">
          <div className="chat-heading">
            <div className="activity-icon">
              <Workflow size={20} />
            </div>
            <div>
              <strong>Operations supervisor</strong>
              <small>Knowledge · Support · Scheduling · Operations</small>
            </div>
            <span className="online-dot" />
          </div>
          <div className="messages">
            {messages.isFetching && !messages.data && id ? (
              <Loading />
            ) : !messages.data?.messages.length && !optimistic ? (
              <div className="chat-welcome">
                <span className="welcome-icon">
                  <Workflow size={32} />
                </span>
                <h2>What can we get done?</h2>
                <p>
                  Retrieve company knowledge, open a support ticket or
                  coordinate your next task.
                </p>
                {settings.data?.provider === 'demo' && (
                  <p className="demo-note">
                    Demo mode uses explicit commands and local document search.
                    Natural-language actions require the OpenAI provider.
                  </p>
                )}
                <div className="suggestions">
                  {[
                    'What is our refund policy?',
                    'List open tickets',
                    'Create task: Review support queue',
                  ].map((prompt) => (
                    <button
                      disabled={!writable}
                      key={prompt}
                      onClick={() => setInput(prompt)}
                    >
                      {prompt}
                      <ArrowRight size={15} />
                    </button>
                  ))}
                </div>
                <details className="command-help">
                  <summary>Demo tool command examples</summary>
                  <code>{'/tool search_customers {"query":"Acme"}'}</code>
                  <code>{'/tool get_business_information {}'}</code>
                  <p>Use exact record IDs from your workspace for writes.</p>
                </details>
              </div>
            ) : (
              messages.data?.messages.map((message) => (
                <div
                  key={message.id}
                  className={`message message-${message.role}`}
                >
                  <div className="message-avatar">
                    {message.role === 'user' ? 'You' : <Workflow size={18} />}
                  </div>
                  <div className="message-body">
                    <strong>
                      {message.role === 'user' ? 'You' : 'Operations assistant'}
                    </strong>
                    <div className="prose">
                      <ReactMarkdown>{message.content}</ReactMarkdown>
                    </div>
                    {message.citations?.length > 0 && (
                      <div className="citations">
                        {message.citations.map((source, i) => (
                          <details key={source.chunk_id}>
                            <summary>
                              <FileText size={14} /> [{i + 1}]{' '}
                              {source.document_name}
                              {source.page && ` · page ${source.page}`}
                            </summary>
                            <p>{source.content}</p>
                            <small>Retrieval score: {source.score}</small>
                          </details>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))
            )}
            {optimistic && (
              <div className="message message-user">
                <div className="message-avatar">You</div>
                <div className="message-body">
                  <strong>You</strong>
                  <p>{optimistic}</p>
                </div>
              </div>
            )}
            {events.some((e) => e.type === 'step') && (
              <details className="execution-inspector" open={busy}>
                <summary>
                  <Workflow size={16} /> Execution inspector
                </summary>
                {events
                  .filter((e) => e.type === 'step')
                  .map((event, i) => (
                    <div key={i}>
                      <CheckCircle2 size={14} />{' '}
                      {event.data.node?.replace(/_/g, ' ')}
                    </div>
                  ))}
                {runId && <Link to={`/runs/${runId}`}>View run details</Link>}
              </details>
            )}
            {pending && (
              <div className="notice">
                This workflow is waiting for human approval.
                <Link to="/approvals">
                  Review proposed action <ArrowRight size={15} />
                </Link>
              </div>
            )}
            {busy && (
              <div className="working">
                <span className="online-dot" /> Workflow in progress…
              </div>
            )}
            {error !== undefined && <ErrorState error={error} />}
            {messages.error && <ErrorState error={messages.error} />}
            <div ref={bottom} />
          </div>
          <form
            className="composer"
            onSubmit={(e) => {
              e.preventDefault()
              void send()
            }}
          >
            <textarea
              aria-label="Message"
              rows={2}
              placeholder={
                writable
                  ? 'Ask a question or describe an action…'
                  : 'Your viewer role can inspect conversations.'
              }
              value={input}
              disabled={!writable || busy}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  void send()
                }
              }}
            />
            <div>
              <small>
                Actions are validated and recorded. Sensitive changes need
                approval.
              </small>
              <Button
                aria-label="Send message"
                disabled={!writable || busy || !input.trim()}
              >
                <Send size={17} />
              </Button>
            </div>
          </form>
        </section>
      </div>
    </>
  )
}
