import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { FileText, Upload, Trash2, Search, RotateCw } from 'lucide-react'
import { api, write } from '../services/api'
import type { Citation, Page } from '../types'
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

export function Knowledge({
  searchOnly = false,
  manage,
}: {
  searchOnly?: boolean
  manage: boolean
}) {
  const client = useQueryClient()
  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<Citation[] | null>(null)
  const [error, setError] = useState<unknown>()
  const [busy, setBusy] = useState(false)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [deleteId, setDeleteId] = useState('')
  const [filter, setFilter] = useState('')
  const [topK, setTopK] = useState(5)
  const [threshold, setThreshold] = useState(0.15)
  const documents = useQuery({
    queryKey: ['documents', filter],
    queryFn: () =>
      api<Page>(`/documents?limit=100&q=${encodeURIComponent(filter)}`),
    refetchInterval: 5000,
  })
  return (
    <>
      <Header
        eyebrow="KNOWLEDGE"
        title={searchOnly ? 'Knowledge search' : 'Company knowledge'}
        description={
          searchOnly
            ? 'Inspect actual source passages and retrieval scores.'
            : 'Turn your documents into evidence your agents can use.'
        }
        action={
          !searchOnly &&
          manage && (
            <Button onClick={() => setUploadOpen(true)}>
              <Upload size={17} /> Upload document
            </Button>
          )
        }
      />
      {error !== undefined && <ErrorState error={error} />}
      <section className="card knowledge-search">
        <h2>Find an answer in your documents</h2>
        <p>
          Results stay inside your organization and include their source
          references.
        </p>
        <form
          onSubmit={async (e) => {
            e.preventDefault()
            setBusy(true)
            setError(undefined)
            try {
              const result = await write<{ hits: Citation[] }>(
                '/knowledge/search',
                { query, top_k: topK, threshold },
              )
              setHits(result.hits)
            } catch (e) {
              setError(e)
            } finally {
              setBusy(false)
            }
          }}
        >
          <div className="search-field">
            <Search size={18} />
            <input
              aria-label="Knowledge question"
              required
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search policies, product guides or operating procedures…"
            />
          </div>
          <Button disabled={busy}>
            {busy ? 'Searching…' : 'Search knowledge'}
          </Button>
          <details>
            <summary>Retrieval settings</summary>
            <label>
              Maximum results
              <input
                type="number"
                min={1}
                max={20}
                value={topK}
                onChange={(e) => setTopK(Number(e.target.value))}
              />
            </label>
            <label>
              Similarity threshold
              <input
                type="number"
                step={0.05}
                min={0}
                max={1}
                value={threshold}
                onChange={(e) => setThreshold(Number(e.target.value))}
              />
            </label>
          </details>
        </form>
        {hits &&
          (hits.length ? (
            <div className="search-results">
              {hits.map((hit, i) => (
                <article key={hit.chunk_id}>
                  <div>
                    <FileText size={17} />
                    <strong>
                      [{i + 1}] {hit.document_name}
                    </strong>
                    <Badge>{`Score ${hit.score}`}</Badge>
                  </div>
                  <p>{hit.content}</p>
                  <small>
                    {hit.page ? `Page ${hit.page} · ` : ''}Document{' '}
                    {hit.document_id.slice(0, 8)}
                  </small>
                </article>
              ))}
            </div>
          ) : (
            <Empty title="Insufficient source coverage">
              No passages met your threshold. Try a different question or upload
              relevant documents.
            </Empty>
          ))}
      </section>
      {!searchOnly && (
        <section className="card">
          <div className="table-toolbar">
            <h2>Documents</h2>
            <input
              aria-label="Search documents"
              placeholder="Search documents…"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
          </div>
          {documents.isPending ? (
            <Loading />
          ) : documents.error ? (
            <ErrorState error={documents.error} />
          ) : !documents.data.items.length ? (
            <Empty title="Build your knowledge base">
              Upload PDF, Markdown, TXT or DOCX files up to 10 MB.
            </Empty>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Document</th>
                    <th>Ingestion</th>
                    <th>Chunks</th>
                    <th>Provider</th>
                    <th>Uploaded</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {documents.data.items.map((row) => (
                    <tr key={row.id}>
                      <td>
                        <div className="file-name">
                          <FileText size={19} />
                          {text(row.name)}
                        </div>
                        <small className="muted">
                          {Math.ceil(Number(row.size_bytes) / 1024)} KB ·{' '}
                          {text(row.error_code) !== '—' && text(row.error_code)}
                        </small>
                      </td>
                      <td>
                        <Badge>{text(row.status)}</Badge>
                      </td>
                      <td>{text(row.chunk_count)}</td>
                      <td>{text(row.embedding_provider)}</td>
                      <td>{formatDate(row.created_at)}</td>
                      <td>
                        {manage && (
                          <>
                            {row.status === 'failed' && (
                              <Button
                                variant="ghost"
                                aria-label="Retry ingestion"
                                onClick={() =>
                                  void write(`/documents/${row.id}/retry`, {})
                                    .then(() => client.invalidateQueries())
                                    .catch(setError)
                                }
                              >
                                <RotateCw size={16} />
                              </Button>
                            )}
                            <Button
                              variant="ghost"
                              aria-label={`Delete ${text(row.name)}`}
                              onClick={() => setDeleteId(row.id)}
                            >
                              <Trash2 size={16} />
                            </Button>
                          </>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
      <Modal
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        title="Upload knowledge"
        description="Text is extracted in the background. Scanned PDFs require a text layer; OCR is not configured."
      >
        <form
          onSubmit={async (e) => {
            e.preventDefault()
            if (!file) return
            setBusy(true)
            try {
              const body = new FormData()
              body.append('file', file)
              await api('/documents', { method: 'POST', body })
              setUploadOpen(false)
              setFile(null)
              await client.invalidateQueries()
            } catch (e) {
              setError(e)
            } finally {
              setBusy(false)
            }
          }}
        >
          <label className="upload-zone">
            <Upload size={28} />
            Choose a PDF, TXT, Markdown or DOCX file
            <input
              type="file"
              accept=".pdf,.txt,.md,.docx"
              required
              onChange={(e) => setFile(e.target.files?.[0] || null)}
            />
          </label>
          <Button disabled={busy || !file}>
            {busy ? 'Uploading…' : 'Upload document'}
          </Button>
        </form>
      </Modal>
      <Modal
        open={!!deleteId}
        onOpenChange={(open) => {
          if (!open) setDeleteId('')
        }}
        title="Delete document?"
        description="This permanently removes the document and every searchable passage."
      >
        <div className="form-actions">
          <Button variant="outline" onClick={() => setDeleteId('')}>
            Keep document
          </Button>
          <Button
            variant="destructive"
            onClick={async () => {
              try {
                await api(`/documents/${deleteId}`, { method: 'DELETE' })
                setDeleteId('')
                await client.invalidateQueries()
              } catch (e) {
                setError(e)
              }
            }}
          >
            Delete document
          </Button>
        </div>
      </Modal>
    </>
  )
}
