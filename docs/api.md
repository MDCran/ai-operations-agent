# API contract

The versioned API is `/api/v1`. Start the application and use `/docs` for generated request/response schemas and `/openapi.json` for tooling. Public entity schemas omit secret and storage fields.

Login uses `POST /auth/login` with `email`, `password` and an optional `organization_id`. Membership is validated. Accounts with multiple memberships must specify an organization. The response sets an expiring HttpOnly session cookie and returns a CSRF token. `GET /auth/me` restores the token after a page reload. Send `X-CSRF-Token` on authenticated mutations. Logout deletes the persisted session and cookie.

Record/tool writes require an `Idempotency-Key` header, 8–100 characters, scoped to organization and bound to the authenticated user and canonical action/payload digest. Reusing a key for different input returns 409. Keys for unrelated actions must be different. The browser generates UUIDs. The chat API instead uses `request_id` in its body.

List responses are `{items, total, offset, limit}`. Query arguments include `q`, `status`, `sort`, `descending`, `offset` and `limit` (maximum 100). LIKE wildcards in search input are escaped. Invalid records return 404 without distinguishing another tenant's resources.

| Module | Endpoints |
| --- | --- |
| Auth | `POST /auth/login`, `POST /auth/logout`, `GET /auth/me` |
| Customers | `GET/POST /customers`, `GET/PATCH/DELETE /customers/{id}` |
| Support | `GET/POST /tickets`, `GET/PATCH /tickets/{id}`, `POST /tickets/{id}/comments`, `POST /tickets/{id}/draft` |
| Tasks | `GET/POST /tasks`, `PATCH /tasks/{id}` |
| Scheduling | `GET/POST /appointments`, `PATCH /appointments/{id}`, `POST /appointments/{id}/cancel`, `POST /appointments/availability`, `GET /appointment-types` |
| Conversations | `GET/POST /conversations`, `GET /conversations/{id}`, `POST /agents/chat` |
| Runs and tools | `GET /agents/tools`, `GET /agents/runs`, `GET /agents/runs/{id}`, `POST /agents/runs/{id}/retry` |
| Knowledge | `GET/POST /documents`, `DELETE /documents/{id}`, `POST /documents/{id}/retry`, `POST /knowledge/search` |
| Approvals | `GET /approvals`, `POST /approvals/{id}/approve`, `/reject`, `/cancel` |
| Administration | `GET/PATCH /organization`, `GET/PUT /business-hours`, `GET/POST /team`, `PATCH /team/{id}`, `GET /ai-settings`, `GET /audit-logs` |
| Metrics | `GET /dashboard/summary`, `GET /analytics/overview` |

Protected dashboard mutations return `{status:"pending_approval",run_id}`. This response confirms a proposal, not a completed write. The approval record exposes the action, exact payload, resource/revision, requester, reason and expiry. Poll the run or approval to observe resumed completion. Only the original requester can retry a failed run. The API does not send external customer messages.

## Streaming

`POST /agents/chat` takes `{conversation_id,message,request_id}` and responds with `text/event-stream`. Fetch-based streaming is used so the client can send a POST body and CSRF token. Event payloads are JSON:

```text
event: run
data: {"run_id":"..."}

event: step
data: {"node":"supervisor","run_id":"..."}

event: approval
data: {"approval_id":"...","action":"update_customer"}

event: answer
data: {"text":"...","citations":[]}

event: error
data: {"code":"conflict","message":"The workflow failed. Inspect the run details."}
```

An execution ends with an answer, an approval interrupt, or an error. Already completed duplicate chat requests replay the persisted answer. Progress is real node completion, not simulated typing. Model plans and hidden prompts are never streamed.

Errors use `{error:{code,message,fields?}}`. Validation errors describe field paths and types without echoing submitted values. Internal exceptions and raw provider errors are not exposed.
