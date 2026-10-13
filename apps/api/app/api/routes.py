import json
from datetime import UTC, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, Query, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.auth.security import Actor, authentication, login, passwords
from app.core.config import settings
from app.core.errors import DomainError
from app.db import repository as repo
from app.db.session import get_db
from app.models import entities as m
from app.schemas import contracts as s
from app.schemas import outputs as o
from app.services.business import audit, availability
from app.services.execution import dispatch, start_run
from app.services.knowledge import search, validate_upload
from app.tools.registry import REGISTRY
from app.workers.jobs import ingest_document, resume_workflow
from app.workflows.engine import drive

router = APIRouter(prefix="/api/v1")
DB = Annotated[Session, Depends(get_db)]
Auth = Annotated[Actor, Depends(authentication)]
Key = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=100)]


class Pagination:
    def __init__(
        self,
        offset: int = Query(0, ge=0),
        limit: int = Query(25, ge=1, le=100),
        q: str = Query("", max_length=200),
        status: str | None = Query(None),
        sort: str = "created_at",
        descending: bool = True,
    ):
        self.values = dict(
            offset=offset, limit=limit, query=q, status=status, sort=sort, descending=descending
        )


Page = Annotated[Pagination, Depends()]


@router.post("/auth/login", tags=["Authentication"])
def auth_login(body: s.Login, request: Request, response: Response, db: DB) -> dict:
    return login(db, body, request, response)


@router.post("/auth/logout", tags=["Authentication"])
def logout(actor: Auth, request: Request, response: Response, db: DB) -> dict:
    db.delete(request.state.auth_session)
    db.commit()
    response.delete_cookie("operations_session", path="/")
    return {"ok": True}


@router.get("/auth/me", tags=["Authentication"])
def me(actor: Auth, request: Request, db: DB) -> dict:
    user = db.get(m.User, actor.user_id)
    return {
        "user": repo.serialize(user),
        "role": actor.role,
        "organization": repo.serialize(db.get(m.Organization, actor.organization_id)),
        "csrf_token": request.state.auth_session.csrf_token,
    }


@router.get("/customers", response_model=o.Paginated[o.CustomerResponse], tags=["CRM"])
def customers(db: DB, actor: Auth, pagination: Page) -> dict:
    return repo.page(db, m.Customer, actor, **pagination.values)


@router.post("/customers", response_model=o.CustomerResponse | o.ApprovalPending, tags=["CRM"])
def customer_create(body: s.CustomerCreate, db: DB, actor: Auth, key: Key) -> dict:
    return dispatch(db, actor, "create_customer", body.model_dump(mode="json"), key)


@router.get("/customers/{id}", tags=["CRM"])
def customer_detail(id: str, db: DB, actor: Auth) -> dict:
    row = repo.get(db, m.Customer, actor, id)
    return {
        "customer": repo.serialize(row),
        "tickets": [
            repo.serialize(t)
            for t in db.scalars(
                select(m.Ticket).where(
                    m.Ticket.organization_id == actor.organization_id, m.Ticket.customer_id == id
                )
            ).all()
        ],
        "appointments": [
            repo.serialize(a)
            for a in db.scalars(
                select(m.Appointment).where(
                    m.Appointment.organization_id == actor.organization_id, m.Appointment.customer_id == id
                )
            ).all()
        ],
    }


@router.patch("/customers/{id}", response_model=o.CustomerResponse | o.ApprovalPending, tags=["CRM"])
def customer_update(id: str, body: s.CustomerPatch, db: DB, actor: Auth, key: Key) -> dict:
    return dispatch(
        db,
        actor,
        "update_customer",
        {"id": id, "changes": body.model_dump(mode="json", exclude_unset=True)},
        key,
    )


@router.delete("/customers/{id}", tags=["CRM"])
def customer_delete(id: str, db: DB, actor: Auth, key: Key) -> dict:
    return dispatch(db, actor, "delete_customer", {"id": id}, key)


@router.get("/tickets", response_model=o.Paginated[o.TicketResponse], tags=["Support"])
def tickets(db: DB, actor: Auth, pagination: Page) -> dict:
    return repo.page(db, m.Ticket, actor, **pagination.values)


@router.post("/tickets", response_model=o.TicketResponse | o.ApprovalPending, tags=["Support"])
def ticket_create(body: s.TicketCreate, db: DB, actor: Auth, key: Key) -> dict:
    return dispatch(db, actor, "create_ticket", body.model_dump(mode="json"), key)


@router.get("/tickets/{id}", tags=["Support"])
def ticket_detail(id: str, db: DB, actor: Auth) -> dict:
    return {
        "ticket": repo.serialize(repo.get(db, m.Ticket, actor, id)),
        "comments": [
            repo.serialize(c)
            for c in db.scalars(
                select(m.TicketComment)
                .where(
                    m.TicketComment.organization_id == actor.organization_id, m.TicketComment.ticket_id == id
                )
                .order_by(m.TicketComment.created_at)
            ).all()
        ],
    }


@router.patch("/tickets/{id}", response_model=o.TicketResponse | o.ApprovalPending, tags=["Support"])
def ticket_update(id: str, body: s.TicketPatch, db: DB, actor: Auth, key: Key) -> dict:
    return dispatch(
        db,
        actor,
        "update_ticket",
        {"id": id, "changes": body.model_dump(mode="json", exclude_unset=True)},
        key,
    )


@router.post("/tickets/{id}/comments", tags=["Support"])
def add_comment(id: str, body: s.CommentCreate, db: DB, actor: Auth) -> dict:
    actor.require("write")
    repo.get(db, m.Ticket, actor, id)
    row = m.TicketComment(
        organization_id=actor.organization_id, ticket_id=id, author_id=actor.user_id, body=body.body
    )
    db.add(row)
    db.flush()
    audit(db, actor, "ticket_comment", row.id)
    db.commit()
    return repo.serialize(row)


@router.post("/tickets/{id}/draft", tags=["Support"])
def ticket_draft(id: str, db: DB, actor: Auth, key: Key) -> dict:
    ticket = repo.get(db, m.Ticket, actor, id)
    conversation = m.Conversation(
        organization_id=actor.organization_id, user_id=actor.user_id, title="Draft: " + ticket.title[:100]
    )
    db.add(conversation)
    db.flush()
    run = start_run(
        db, actor, conversation.id, "Draft a response using uploaded evidence: " + ticket.description, key
    )
    list(drive(run.id, "Draft a response using uploaded evidence: " + ticket.description))
    db.refresh(run)
    return {"run_id": run.id, "draft": run.outcome, "status": run.status}


@router.get("/tasks", response_model=o.Paginated[o.TaskResponse], tags=["Tasks"])
def tasks(db: DB, actor: Auth, pagination: Page) -> dict:
    return repo.page(db, m.Task, actor, **pagination.values)


@router.post("/tasks", response_model=o.TaskResponse | o.ApprovalPending, tags=["Tasks"])
def task_create(body: s.TaskCreate, db: DB, actor: Auth, key: Key) -> dict:
    return dispatch(db, actor, "create_task", body.model_dump(mode="json"), key)


@router.patch("/tasks/{id}", response_model=o.TaskResponse | o.ApprovalPending, tags=["Tasks"])
def task_update(id: str, body: s.TaskPatch, db: DB, actor: Auth, key: Key) -> dict:
    return dispatch(
        db, actor, "update_task", {"id": id, "changes": body.model_dump(mode="json", exclude_unset=True)}, key
    )


@router.get("/appointments", response_model=o.Paginated[o.AppointmentResponse], tags=["Scheduling"])
def appointments(db: DB, actor: Auth, pagination: Page) -> dict:
    return repo.page(db, m.Appointment, actor, **pagination.values)


@router.post("/appointments", response_model=o.AppointmentResponse | o.ApprovalPending, tags=["Scheduling"])
def appointment_create(body: s.AppointmentCreate, db: DB, actor: Auth, key: Key) -> dict:
    return dispatch(db, actor, "create_appointment", body.model_dump(mode="json"), key)


@router.patch(
    "/appointments/{id}", response_model=o.AppointmentResponse | o.ApprovalPending, tags=["Scheduling"]
)
def appointment_move(id: str, body: s.AppointmentMove, db: DB, actor: Auth, key: Key) -> dict:
    return dispatch(
        db, actor, "reschedule_appointment", {"id": id, "starts_at": body.starts_at.isoformat()}, key
    )


@router.post("/appointments/{id}/cancel", tags=["Scheduling"])
def appointment_cancel(id: str, db: DB, actor: Auth, key: Key) -> dict:
    return dispatch(db, actor, "cancel_appointment", {"id": id}, key)


@router.post("/appointments/availability", response_model=o.AvailabilityResponse, tags=["Scheduling"])
def available_slots(body: s.Availability, db: DB, actor: Auth) -> dict:
    return availability(db, actor, body)


@router.get("/appointment-types", response_model=o.Paginated[o.AppointmentTypeResponse], tags=["Scheduling"])
def appointment_types(db: DB, actor: Auth) -> dict:
    return repo.page(db, m.AppointmentType, actor, limit=100)


@router.post("/appointment-types", response_model=o.AppointmentTypeResponse, tags=["Scheduling"])
def appointment_type_create(body: s.AppointmentTypeCreate, db: DB, actor: Auth) -> dict:
    actor.require("manage")
    row = m.AppointmentType(organization_id=actor.organization_id, **body.model_dump())
    db.add(row)
    db.flush()
    audit(db, actor, "appointment_type_created", row.id, body.model_fields_set)
    db.commit()
    return repo.serialize(row)


@router.patch("/appointment-types/{id}", response_model=o.AppointmentTypeResponse, tags=["Scheduling"])
def appointment_type_update(id: str, body: s.AppointmentTypePatch, db: DB, actor: Auth) -> dict:
    actor.require("manage")
    row = repo.get(db, m.AppointmentType, actor, id, lock=True)
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(row, field, value)
    audit(db, actor, "appointment_type_updated", row.id, changes)
    db.commit()
    return repo.serialize(row)


@router.get("/conversations", response_model=o.Paginated[o.ConversationResponse], tags=["AI workspace"])
def conversations(db: DB, actor: Auth, pagination: Page) -> dict:
    return repo.page(db, m.Conversation, actor, **pagination.values)


@router.post("/conversations", response_model=o.ConversationResponse, tags=["AI workspace"])
def conversation_create(db: DB, actor: Auth) -> dict:
    actor.require("write")
    row = m.Conversation(organization_id=actor.organization_id, user_id=actor.user_id)
    db.add(row)
    db.commit()
    return repo.serialize(row)


@router.get("/conversations/{id}", tags=["AI workspace"])
def conversation_detail(id: str, db: DB, actor: Auth) -> dict:
    row = repo.get(db, m.Conversation, actor, id)
    messages = db.scalars(
        select(m.Message)
        .where(m.Message.organization_id == actor.organization_id, m.Message.conversation_id == id)
        .order_by(m.Message.created_at)
        .limit(500)
    ).all()
    return {"conversation": repo.serialize(row), "messages": [repo.serialize(x) for x in messages]}


@router.post("/agents/chat", tags=["AI workspace"])
def chat(body: s.Chat, db: DB, actor: Auth) -> StreamingResponse:
    run = start_run(db, actor, body.conversation_id, body.message, body.request_id)

    def events():
        yield "event: run\ndata: " + json.dumps({"run_id": run.id}) + "\n\n"
        if run.status in {"succeeded", "rejected"}:
            yield "event: answer\ndata: " + json.dumps(run.outcome) + "\n\n"
            return
        if run.status == "pending_approval":
            approval = db.scalar(select(m.Approval).where(m.Approval.run_id == run.id))
            yield (
                "event: approval\ndata: "
                + json.dumps({"approval_id": approval.id, "action": approval.action})
                + "\n\n"
            )
            return
        for event in drive(run.id, body.message):
            yield "event: " + event["type"] + "\ndata: " + json.dumps(event["data"]) + "\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/agents/tools", tags=["AI workspace"])
def tools(actor: Auth) -> dict:
    return {
        "items": [
            {
                "name": t.name,
                "description": t.description,
                "writes": t.writes,
                "input_schema": t.input_schema.model_json_schema(),
                "output_schema": t.output_schema.model_json_schema(),
            }
            for t in REGISTRY.values()
        ]
    }


@router.get("/agents/runs", response_model=o.Paginated[o.RunResponse], tags=["Monitoring"])
def runs(db: DB, actor: Auth, pagination: Page) -> dict:
    return repo.page(db, m.AgentRun, actor, **pagination.values)


@router.get("/agents/runs/{id}", tags=["Monitoring"])
def run_detail(id: str, db: DB, actor: Auth) -> dict:
    run = repo.get(db, m.AgentRun, actor, id)
    return {
        "run": repo.serialize(run),
        "steps": [
            repo.serialize(x)
            for x in db.scalars(
                select(m.AgentStep)
                .where(m.AgentStep.organization_id == actor.organization_id, m.AgentStep.run_id == id)
                .order_by(m.AgentStep.created_at)
            ).all()
        ],
        "tools": [
            repo.serialize(x)
            for x in db.scalars(
                select(m.ToolExecution).where(
                    m.ToolExecution.organization_id == actor.organization_id, m.ToolExecution.run_id == id
                )
            ).all()
        ],
        "approvals": [
            repo.serialize(x)
            for x in db.scalars(
                select(m.Approval).where(
                    m.Approval.organization_id == actor.organization_id, m.Approval.run_id == id
                )
            ).all()
        ],
    }


@router.post("/agents/runs/{id}/retry", tags=["Monitoring"])
def retry_run(id: str, db: DB, actor: Auth) -> dict:
    actor.require("write")
    run = repo.get(db, m.AgentRun, actor, id, lock=True)
    if run.requester_id != actor.user_id or run.status != "failed":
        raise DomainError("invalid_retry", "Only the requester can retry a failed run.", 409)
    run.status = "running"
    run.error_code = None
    db.commit()
    list(drive(run.id))
    db.refresh(run)
    return repo.serialize(run)


@router.get("/documents", response_model=o.Paginated[o.DocumentResponse], tags=["Knowledge"])
def documents(db: DB, actor: Auth, pagination: Page) -> dict:
    return repo.page(db, m.Document, actor, **pagination.values)


@router.post("/documents", response_model=o.DocumentResponse, tags=["Knowledge"])
async def document_upload(db: DB, actor: Auth, file: UploadFile = File(...)) -> dict:
    actor.require("manage")
    data = await file.read(settings().max_upload_bytes + 1)
    name = Path((file.filename or "document.txt").replace("\\", "/")).name[:200]
    validate_upload(name, data)
    storage_key = m.uid() + Path(name).suffix.lower()
    root = Path(settings().upload_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / storage_key
    row = m.Document(
        organization_id=actor.organization_id,
        name=name,
        storage_key=storage_key,
        size_bytes=len(data),
        embedding_provider=settings().ai_provider,
        embedding_model=settings().embedding_model
        if settings().ai_provider == "openai"
        else "lexical-hash-v1",
    )
    try:
        path.write_bytes(data)
        db.add(row)
        db.flush()
        audit(db, actor, "document_uploaded", row.id)
        db.commit()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    try:
        ingest_document.delay(row.id)
    except Exception:
        pass  # Persisted outbox state is recovered by the scheduler.
    return repo.serialize(row)


@router.post("/documents/{id}/retry", tags=["Knowledge"])
def document_retry(id: str, db: DB, actor: Auth) -> dict:
    actor.require("manage")
    row = repo.get(db, m.Document, actor, id, lock=True)
    if row.embedding_provider != settings().ai_provider:
        raise DomainError(
            "provider_changed", "Re-upload the file for the configured embedding provider.", 409
        )
    row.status = "queued"
    row.error_code = None
    db.commit()
    ingest_document.delay(row.id)
    return repo.serialize(row)


@router.delete("/documents/{id}", tags=["Knowledge"])
def document_delete(id: str, db: DB, actor: Auth) -> dict:
    actor.require("manage")
    row = repo.get(db, m.Document, actor, id, lock=True)
    key = row.storage_key
    db.delete(row)
    audit(db, actor, "document_deleted", id)
    db.commit()  # FK cascade removes searchable chunks atomically.
    (Path(settings().upload_dir) / key).unlink(missing_ok=True)
    return {"deleted": True}


@router.post("/knowledge/search", response_model=o.SearchResponse, tags=["Knowledge"])
def knowledge_search(body: s.Search, db: DB, actor: Auth) -> dict:
    return search(db, actor, body)


@router.get("/approvals", response_model=o.Paginated[o.ApprovalResponse], tags=["Approvals"])
def approvals(db: DB, actor: Auth, pagination: Page) -> dict:
    actor.require("write")
    return repo.page(db, m.Approval, actor, **pagination.values)


def decide(id, decision, db, actor):
    actor.require("approve")
    request = repo.get(db, m.Approval, actor, id, lock=True)
    if request.status == "pending":
        request.status = "expired" if request.expires_at <= m.now() else decision
        request.decided_by = actor.user_id
        audit(db, actor, "approval_" + request.status, request.id)
        db.commit()
    elif request.status not in {decision, "expired"} and not (
        decision == "approved" and request.status == "executed"
    ):
        raise DomainError("approval_decided", "The approval already has a different decision.", 409)
    try:
        resume_workflow.delay(request.run_id)
    except Exception:
        pass
    return repo.serialize(request)


@router.post("/approvals/{id}/approve", tags=["Approvals"])
def approve(id: str, db: DB, actor: Auth) -> dict:
    return decide(id, "approved", db, actor)


@router.post("/approvals/{id}/reject", tags=["Approvals"])
def reject(id: str, db: DB, actor: Auth) -> dict:
    return decide(id, "rejected", db, actor)


@router.post("/approvals/{id}/cancel", tags=["Approvals"])
def approval_cancel(id: str, db: DB, actor: Auth) -> dict:
    request = repo.get(db, m.Approval, actor, id, lock=True)
    if actor.user_id != request.requester_id:
        actor.require("approve")
    if request.status != "pending":
        raise DomainError("approval_decided", "Only a pending approval can be cancelled.", 409)
    request.status = "cancelled"
    audit(db, actor, "approval_cancelled", id)
    db.commit()
    resume_workflow.delay(request.run_id)
    return repo.serialize(request)


@router.get("/dashboard/summary", tags=["Monitoring"])
@router.get("/analytics/overview", tags=["Monitoring"])
def summary(db: DB, actor: Auth) -> dict:
    org_id = actor.organization_id

    def count(model, *filters):
        return db.scalar(
            select(func.count()).select_from(model).where(model.organization_id == org_id, *filters)
        )

    run_total = count(m.AgentRun)
    completed = count(m.AgentRun, m.AgentRun.status == "succeeded")
    from zoneinfo import ZoneInfo

    zone = ZoneInfo(db.get(m.Organization, org_id).timezone)
    today = m.now().astimezone(zone)
    week = (
        (today - timedelta(days=today.weekday()))
        .replace(hour=0, minute=0, second=0, microsecond=0)
        .astimezone(UTC)
    )
    tokens = db.execute(
        select(
            func.coalesce(func.sum(m.AgentRun.input_tokens), 0),
            func.coalesce(func.sum(m.AgentRun.output_tokens), 0),
            func.coalesce(func.avg(m.AgentRun.duration_ms), 0),
        ).where(m.AgentRun.organization_id == org_id)
    ).one()
    config = settings()
    cost = (
        (tokens[0] * config.model_input_cost_per_million + tokens[1] * config.model_output_cost_per_million)
        / 1_000_000
        if config.model_input_cost_per_million is not None
        and config.model_output_cost_per_million is not None
        else None
    )
    trends = db.execute(
        select(func.date(m.AgentRun.created_at), func.count())
        .where(m.AgentRun.organization_id == org_id, m.AgentRun.created_at > m.now() - timedelta(days=14))
        .group_by(func.date(m.AgentRun.created_at))
        .order_by(func.date(m.AgentRun.created_at))
    ).all()
    statuses = db.execute(
        select(m.Ticket.status, func.count())
        .where(m.Ticket.organization_id == org_id)
        .group_by(m.Ticket.status)
    ).all()
    tools = db.execute(
        select(m.ToolExecution.tool, func.count())
        .where(m.ToolExecution.organization_id == org_id)
        .group_by(m.ToolExecution.tool)
    ).all()
    return {
        "customers": count(m.Customer),
        "open_tickets": count(m.Ticket, m.Ticket.status.in_(["open", "in_progress", "pending"])),
        "appointments_this_week": count(
            m.Appointment,
            m.Appointment.starts_at >= week,
            m.Appointment.starts_at < week + timedelta(days=7),
            m.Appointment.status != "cancelled",
        ),
        "pending_approvals": count(
            m.Approval, m.Approval.status == "pending", m.Approval.expires_at > m.now()
        ),
        "runs": run_total,
        "success_rate": round(completed / run_total * 100, 1) if run_total else None,
        "failed_runs": count(m.AgentRun, m.AgentRun.status == "failed"),
        "input_tokens": tokens[0],
        "output_tokens": tokens[1],
        "average_latency_ms": round(float(tokens[2])),
        "estimated_cost": cost,
        "run_trends": [{"date": str(d), "runs": n} for d, n in trends],
        "ticket_distribution": [{"status": status, "count": n} for status, n in statuses],
        "tool_counts": [{"tool": name, "count": n} for name, n in tools],
        "recent_activity": repo.page(db, m.AgentRun, actor, limit=6)["items"],
    }


@router.get("/audit-logs", response_model=o.Paginated[o.AuditResponse], tags=["Administration"])
def audit_logs(db: DB, actor: Auth, pagination: Page) -> dict:
    actor.require("audit")
    return repo.page(db, m.AuditLog, actor, **pagination.values)


@router.get("/organization", tags=["Administration"])
def organization(db: DB, actor: Auth) -> dict:
    return repo.serialize(db.get(m.Organization, actor.organization_id))


@router.patch("/organization", tags=["Administration"])
def organization_update(body: s.OrganizationPatch, db: DB, actor: Auth) -> dict:
    actor.require("manage")
    if any(name not in REGISTRY or not REGISTRY[name].writes for name in body.approval_tools):
        raise DomainError("invalid_tool", "Approval settings must name registered write tools.")
    row = db.get(m.Organization, actor.organization_id)
    for field, value in body.model_dump().items():
        setattr(row, field, value)
    audit(db, actor, "organization_updated", row.id, body.model_fields_set)
    db.commit()
    return repo.serialize(row)


@router.get("/business-hours", tags=["Administration"])
def hours(db: DB, actor: Auth) -> dict:
    return repo.page(db, m.BusinessHours, actor)


@router.put("/business-hours", tags=["Administration"])
def update_hours(body: s.HoursUpdate, db: DB, actor: Auth) -> dict:
    actor.require("manage")
    if len({h.weekday for h in body.hours}) != len(body.hours) or any(
        h.close_minute <= h.open_minute for h in body.hours
    ):
        raise DomainError("invalid_hours", "Each weekday needs one valid opening interval.")
    db.execute(delete(m.BusinessHours).where(m.BusinessHours.organization_id == actor.organization_id))
    db.add_all([m.BusinessHours(organization_id=actor.organization_id, **h.model_dump()) for h in body.hours])
    audit(db, actor, "business_hours_updated", actor.organization_id)
    db.commit()
    return hours(db, actor)


@router.get("/team", tags=["Administration"])
def team(db: DB, actor: Auth) -> dict:
    rows = db.execute(
        select(m.Membership, m.User)
        .join(m.User, m.User.id == m.Membership.user_id)
        .where(m.Membership.organization_id == actor.organization_id)
    ).all()
    return {
        "items": [
            {"id": member.id, "user_id": user.id, "name": user.name, "email": user.email, "role": member.role}
            for member, user in rows
        ]
    }


@router.post("/team", tags=["Administration"])
def add_member(body: s.MemberCreate, db: DB, actor: Auth) -> dict:
    actor.require("manage")
    user = m.User(name=body.name, email=str(body.email).lower(), password_hash=passwords.hash(body.password))
    # Existing accounts must use a future invitation/acceptance flow; never overwrite their password.
    db.add(user)
    db.flush()
    member = m.Membership(organization_id=actor.organization_id, user_id=user.id, role=body.role)
    db.add(member)
    db.flush()
    audit(db, actor, "member_created", member.id, ["role"])
    db.commit()
    return {"id": member.id, "name": user.name, "email": user.email, "role": member.role}


@router.patch("/team/{id}", tags=["Administration"])
def change_role(id: str, body: s.RolePatch, db: DB, actor: Auth) -> dict:
    actor.require("manage")
    member = repo.get(db, m.Membership, actor, id, lock=True)
    if (
        member.role == "owner"
        or member.user_id == actor.user_id
        or actor.role == "admin"
        and body.role == "admin"
    ):
        raise DomainError("forbidden", "This role change requires an owner and cannot change the owner.", 403)
    member.role = body.role
    audit(db, actor, "member_role_updated", member.id, ["role"])
    db.commit()
    return repo.serialize(member)


@router.get("/ai-settings", tags=["Administration"])
def ai_settings(actor: Auth) -> dict:
    return {
        "provider": settings().ai_provider,
        "model": settings().chat_model if settings().ai_provider == "openai" else "deterministic-commands",
        "embedding_model": settings().embedding_model
        if settings().ai_provider == "openai"
        else "lexical-hash-v1",
        "tracing_enabled": settings().langsmith_tracing,
        "configuration": "Environment variables; restart services to change.",
    }
