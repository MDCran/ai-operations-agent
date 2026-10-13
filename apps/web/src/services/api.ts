import type { StreamEvent } from '../types'

let csrfToken = ''
export function setCsrf(token: string) {
  csrfToken = token
}
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code: string,
  ) {
    super(message)
  }
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers)
  if (options.body && !(options.body instanceof FormData))
    headers.set('Content-Type', 'application/json')
  if (options.method && options.method !== 'GET') {
    headers.set('X-CSRF-Token', csrfToken)
    if (!headers.has('Idempotency-Key'))
      headers.set('Idempotency-Key', crypto.randomUUID())
  }
  const response = await fetch(`/api/v1${path}`, {
    ...options,
    headers,
    credentials: 'same-origin',
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({
      error: { message: 'The service is unavailable.', code: 'unavailable' },
    }))
    throw new ApiError(
      body.error?.message || 'Request failed.',
      response.status,
      body.error?.code || 'unknown',
    )
  }
  return response.json() as Promise<T>
}
export function write<T>(
  path: string,
  body: unknown,
  method = 'POST',
): Promise<T> {
  return api<T>(path, { method, body: JSON.stringify(body) })
}
export async function streamChat(
  body: unknown,
  onEvent: (event: StreamEvent) => void,
  signal: AbortSignal,
) {
  const response = await fetch('/api/v1/agents/chat', {
    method: 'POST',
    credentials: 'same-origin',
    signal,
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.error?.message || 'Unable to start workflow.')
  }
  const reader = response.body?.getReader()
  if (!reader) throw new Error('Streaming is unavailable.')
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
    let boundary: number
    while ((boundary = buffer.indexOf('\n\n')) >= 0) {
      const block = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      const lines = block.split('\n')
      const type =
        lines.find((line) => line.startsWith('event: '))?.slice(7) || 'message'
      const data = lines
        .filter((line) => line.startsWith('data: '))
        .map((line) => line.slice(6))
        .join('\n')
      if (data) onEvent({ type, data: JSON.parse(data) })
    }
  }
}
