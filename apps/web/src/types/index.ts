export interface Entity {
  id: string
  created_at: string
  updated_at: string
  organization_id: string
  [key: string]: unknown
}
export interface Customer extends Entity {
  first_name: string
  last_name: string
  email: string
  company: string
  status: string
}
export interface Conversation extends Entity {
  title: string
}
export interface Citation {
  chunk_id: string
  document_id: string
  document_name: string
  page: number | null
  content: string
  score: number
}
export interface Message extends Entity {
  role: string
  content: string
  citations: Citation[]
  run_id: string | null
}
export interface Approval extends Entity {
  action: string
  payload: Record<string, unknown>
  status: string
  reason: string
  resource_id: string | null
  requester_id: string
  run_id: string
  expires_at: string
}
export interface Page<T = Entity> {
  items: T[]
  total: number
  offset: number
  limit: number
}
export interface Organization extends Entity {
  name: string
  timezone: string
  business_information: string
  approval_tools: string[]
}
export interface Me {
  user: { id: string; name: string; email: string }
  role: 'owner' | 'admin' | 'agent' | 'viewer'
  organization: Organization
  csrf_token: string
}
export interface Summary {
  customers: number
  open_tickets: number
  appointments_this_week: number
  pending_approvals: number
  runs: number
  success_rate: number | null
  failed_runs: number
  input_tokens: number
  output_tokens: number
  average_latency_ms: number
  estimated_cost: number | null
  run_trends: { date: string; runs: number }[]
  ticket_distribution: { status: string; count: number }[]
  tool_counts: { tool: string; count: number }[]
  recent_activity: Entity[]
}
export interface StreamEvent {
  type: string
  data: {
    node?: string
    run_id?: string
    text?: string
    citations?: Citation[]
    approval_id?: string
    message?: string
  }
}
