# Security policy

Report vulnerabilities through [GitHub private vulnerability reporting](https://github.com/MDCran/ai-operations-agent/security/advisories/new). Do not include passwords, keys, customer records or session cookies in public issues. Only the latest `main` is supported while the project is pre-1.0.

## Permission matrix

| Permission | Owner | Admin | Agent | Viewer |
| --- | --- | --- | --- | --- |
| Read organization operations, knowledge, conversations and runs | Yes | Yes | Yes | Yes |
| Create/update customers, tickets, tasks and bookings | Yes | Yes | Yes | No |
| Propose protected actions and inspect approvals | Yes | Yes | Yes | No |
| Approve/reject protected actions | Yes | Yes | No | No |
| Cancel one's pending proposal | Yes | Yes | Yes | No |
| Manage documents, business settings, hours and accounts | Yes | Yes | No | No |
| Change another member to admin | Yes | No | No | No |
| Change owner role or one's own role | No | No | No | No |
| Read audit logs | Yes | Yes | No | No |

Organization members can inspect shared organizational conversation history. This is intentional team visibility; the system does not offer private per-user conversations. An owner may approve their own proposal; separation of duties is not enforced by this initial policy.

## Enforced controls

- Argon2id password hashing through `pwdlib`; random opaque session tokens are stored as SHA-256 hashes. Session expiry is twelve hours by default. Logout and membership/active-state changes revoke access immediately at authentication.
- Production cookies require HTTPS and are Secure, HttpOnly and SameSite Strict. CSRF tokens protect authenticated mutations; supplied browser origins must be allowlisted. Login is rate-limited by client and normalized email.
- Redis-backed limits work across API workers and fail closed if Redis is unavailable. Do not trust arbitrary forwarded client headers at the ingress.
- Actors derive from database membership. Client-supplied roles are never accepted. Tenant filtering is applied to CRUD, tool calls, vectors, metrics, history and audit queries. Composite foreign keys protect related records across organizations. Database RLS is not implemented; DB credentials belong to trusted backend processes only.
- Writes use typed tool schemas, immutable approval digests and transactional idempotency. Authorization is rechecked after a pause. Audit logs contain IDs and changed field names, not customer payloads.
- Uploaded files use random storage keys, size/type limits, extraction bounds and background worker time limits. PDFs need a text layer; encrypted PDFs are rejected. External XML/media fetching and macro execution are not part of ingestion.
- Retrieved content never enters the tool-planning stage. It is untrusted evidence, with validated citation IDs and explicit insufficient-evidence behavior.
- Same-origin web hosting, explicit CORS, restrictive CSP, frame denial and MIME-sniffing protection are configured in the web container. Markdown does not render raw HTML. React escapes displayed payloads.
- Secrets stay in environment configuration and are excluded from the repository, API serializers and dashboard. Provider tracing is optional and has separate privacy implications.

Before a public deployment, use a TLS ingress, dedicated database users, managed secrets, restricted network access, encrypted storage, tested backups, monitored workers and a reviewed retention policy. Rate limits are a baseline, not a complete abuse defense. Add SSO/MFA, password recovery, stronger invitation handling, tenant quotas and independent security review for a commercial service.

No external email/calendar integrations are configured. Future integrations must include least-privilege scopes, explicit approval for external communications, audited idempotent delivery and their own failure reconciliation.
