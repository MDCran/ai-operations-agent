from celery import Celery
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import entities as m

celery = Celery("operations", broker=settings().redis_url, backend=settings().redis_url)
celery.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    task_soft_time_limit=240,
    task_time_limit=300,
    beat_schedule={"recover-work": {"task": "operations.recover", "schedule": 60.0}},
)


@celery.task(name="operations.ingest", autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def ingest_document(document_id):
    from app.services.knowledge import ingest

    ingest(document_id)


@celery.task(name="operations.resume", autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def resume_workflow(run_id):
    from app.workflows.engine import drive

    list(drive(run_id, resume=True))


@celery.task(name="operations.recover")
def recover():
    from datetime import timedelta

    from app.workflows.engine import drive

    with SessionLocal() as db:
        approvals = db.scalars(
            select(m.Approval).where(
                m.Approval.status.in_(["approved", "rejected", "executed", "cancelled", "expired"])
            )
        ).all()
        pending = db.scalars(
            select(m.Approval).where(m.Approval.status == "pending", m.Approval.expires_at < m.now())
        ).all()
        for request in pending:
            request.status = "expired"
        db.commit()
        run_ids = [
            a.run_id for a in approvals + pending if db.get(m.AgentRun, a.run_id).status == "pending_approval"
        ]
        documents = db.scalars(
            select(m.Document).where(m.Document.status.in_(["queued", "processing"]))
        ).all()
        stale = db.scalars(
            select(m.AgentRun).where(
                m.AgentRun.status == "running", m.AgentRun.updated_at < m.now() - timedelta(minutes=5)
            )
        ).all()
    for document in documents:
        ingest_document.delay(document.id)
    for run_id in run_ids:
        resume_workflow.delay(run_id)
    for run in stale:
        list(drive(run.id))
