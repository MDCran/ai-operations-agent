# Deployment and operations

## Local reproducibility

`docker compose up --build -d` starts PostgreSQL/pgvector, Redis, a one-shot migration, FastAPI, Celery worker, Celery scheduler and the web reverse proxy. Migration completion and dependency health gate API startup. The API health endpoint verifies PostgreSQL and Redis; worker and scheduler liveness should be monitored separately.

Use Node 22, Python 3.12 and the committed lockfiles when developing outside containers. `DATABASE_URL` uses SQLAlchemy's `postgresql+psycopg://` form. LangGraph's saver receives the derived ordinary PostgreSQL DSN. Local ports are 55432 and 56379 for database/Redis, 8000 for API and 8080 for the web app.

Production image builds explicitly use the `runtime` target; `test` includes development checks. Container processes run as an unprivileged account. Configure writable upload storage and disable privileged filesystem access.

## AWS-compatible topology

Build API and web images and push them to private ECR repositories. Run API, worker and scheduler as separate ECS/Fargate services in private subnets. Use RDS PostgreSQL 16 with pgvector and btree_gist, ElastiCache Redis, EFS for the current shared-file ingestion implementation, and an HTTPS ALB in front of the web container. The nginx configuration expects `api:8000`; supply private service discovery for that name or render the upstream for your environment. Run exactly one scheduler process; workers and API replicas may scale horizontally.

The [ECS task template](../infrastructure/ecs-api-task.json) is an example to render with your account, region, ECR URI, execution/task roles and Secrets Manager ARNs. It is not provisioned cloud infrastructure. Restrict PostgreSQL/Redis security groups to application services and never expose those services publicly. The Docker Compose database bindings are for local development.

Set `ENVIRONMENT=production`, HTTPS `ALLOWED_ORIGINS`, strong database credentials and server-side provider secrets. Use a separate migration credential to create extensions/tables; runtime users need application/checkpoint DML but do not need superuser privileges. Run `python -m app.db.initialize` as a one-off deployment task before updating services. LangGraph checkpoint migrations are part of this step.

Provision the first production owner interactively, without placing a password in a command line:

```sh
uv run --no-sync python -m app.db.create_owner --organization "Your Company" --email owner@your-domain.example --name "Owner" --timezone America/New_York
```

Model settings are deployment configuration, not browser-editable secrets. Costs are estimated from explicitly configured input/output token prices. Enable tracing only after privacy review. Live model-provider calls have not been certified by the offline suite.

## Recovery and monitoring

Monitor API health, worker availability, scheduler heartbeats, queue depth, queued/failed documents, stale running runs and decided approvals that have not executed. A scheduler sweep runs every minute. It retries persisted undelivered jobs, expires pending approvals and resumes completed decisions. The API's run inspector distinguishes `running`, `pending_approval`, `succeeded`, `rejected` and `failed`.

After a crash, workers recreate graphs using persisted PostgreSQL checkpoints. Replays use transactional tool receipts. A failed resource-version check requires a new reviewed proposal, not mutation of an existing approval payload. The original requester can retry a failed workflow from the run screen when its underlying cause has been repaired. Do not clear checkpoints/idempotency records as a routine fix.

Tune Celery limits for the deployment size: this version uses a 240-second soft limit and 300-second hard limit. PDF extraction runs in worker processes. Slow provider requests and large ingestion jobs may need stricter quotas and isolated worker pools.

## Backups

Back up the complete PostgreSQL database, including checkpoint tables, and the upload volume together. Back up before migrations and test restoring to an isolated environment. Enable encrypted RDS backups/PITR and EFS encryption where applicable. Redis job state is recoverable from database outbox state; Redis still needs durable configuration and operational availability for rate limits/dispatch.

Keep audit retention separate from business record deletion. Rotation of provider/database credentials requires service recreation; session revocation can be performed by deleting the organization's persisted auth sessions through an authorized administrative database operation.

## Known deployment limits

The included configuration does not provision DNS, TLS, cloud accounts or paid infrastructure. External calendar sync, email delivery, OCR, SSO/MFA, password recovery, automatic privacy erasure and multi-resource scheduling require additional implementation. The app is deployment-prepared; it has not been deployed to AWS by this repository build.
