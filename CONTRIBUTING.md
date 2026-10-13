# Contributing

Use Python 3.12, Node 22 and the committed dependency locks. Keep controllers, domain services, repository queries, agent tools and orchestration separate. Never expose a generic SQL/shell tool to an agent.

Run backend integration checks with the isolated `compose.test.yml` stack. It refuses to target any database except `operations_test`; do not repoint tests at business data. Run `uv run ruff check app tests alembic evaluation` and `uv run ruff format --check app tests alembic evaluation` from `apps/api`. Run `npm run build` and the Playwright suite from `apps/web` with a running, seeded disposable demo stack.

New tools need validated input and output schemas, a role-scoped allowlist, tenant-aware domain operations, a clear read/write classification, and transactional write auditing/idempotency. Add security and business-invariant tests rather than tests that merely repeat implementation details. Never treat model output or retrieved text as authorization.

Generate an Alembic migration for schema changes, review indexes/foreign keys/tenant boundaries, and test fresh upgrades and upgrades from the previous revision. Update the API contracts and corresponding frontend types. Preserve source references for retrieval changes and prevent cross-provider vector comparisons.

Open a focused pull request describing the user-facing behavior, key tradeoffs and validation. Disclose which provider behavior was actually tested. Do not commit `.env`, API keys, logs, production data, screenshots of real users or browser traces containing credentials.
