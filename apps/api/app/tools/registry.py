import hashlib
import json
from dataclasses import dataclass
from time import monotonic
from typing import Callable

from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.security import Actor
from app.core.errors import DomainError
from app.db import repository as repo
from app.models import entities as m
from app.schemas import contracts as s
from app.services import business


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: type[BaseModel]
    handler: Callable
    writes: bool = False
    output_schema: type[BaseModel] = s.ToolResult


REGISTRY: dict[str, Tool] = {}


def resource_model(name):
    return (
        m.Customer
        if "customer" in name
        else m.Ticket
        if "ticket" in name
        else m.Task
        if "task" in name
        else m.Appointment
    )


def register(name, description, schema, handler, writes=False):
    from pydantic import create_model

    from app.schemas.outputs import TOOL_OUTPUTS

    output = (
        create_model(name + "Result", data=(TOOL_OUTPUTS[name], ...))
        if name in TOOL_OUTPUTS
        else s.ToolResult
    )
    REGISTRY[name] = Tool(name, description, schema, handler, writes, output)


def payload_hash(name: str, payload: dict) -> str:
    return hashlib.sha256(
        json.dumps({"tool": name, "arguments": payload}, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def requires_approval(db: Session, actor: Actor, name: str, arguments: dict) -> bool:
    organization = db.get(m.Organization, actor.organization_id)
    return (
        name in {"cancel_appointment", "delete_customer"}
        or name in organization.approval_tools
        or name == "update_customer"
        and bool({"email", "status", "notes"} & arguments.get("changes", {}).keys())
    )


def execute(
    db: Session,
    actor: Actor,
    name: str,
    arguments: dict,
    key: str,
    run_id: str | None = None,
    approval: m.Approval | None = None,
    _attempt: int = 0,
):
    tool = REGISTRY.get(name)
    if not tool:
        raise DomainError("unknown_tool", "That operation is unavailable.")
    body = tool.input_schema.model_validate(arguments)
    payload = body.model_dump(mode="json", exclude_unset=True)
    actor.require("write" if tool.writes else "read")
    request_hash = payload_hash(name, payload)
    started = monotonic()
    try:
        # Per-key transaction lock serializes identical calls across processes/retries.
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": actor.organization_id + ":" + key},
        )
        db.execute(text("SET LOCAL statement_timeout = '10000'"))
        prior = db.scalar(
            select(m.IdempotencyRecord).where(
                m.IdempotencyRecord.organization_id == actor.organization_id, m.IdempotencyRecord.key == key
            )
        )
        if prior:
            if prior.request_hash != request_hash or prior.user_id != actor.user_id:
                raise DomainError(
                    "idempotency_conflict", "Request key was already used for a different action.", 409
                )
            db.commit()
            return prior.result
        if tool.writes and (requires_approval(db, actor, name, payload) or approval is not None):
            if (
                not approval
                or approval.status != "approved"
                or approval.action != name
                or approval.payload_hash != request_hash
                or approval.payload != payload
                or approval.organization_id != actor.organization_id
                or approval.requester_id != actor.user_id
            ):
                raise DomainError("approval_required", "This action requires an approved workflow.", 409)
            locked = repo.get(db, m.Approval, actor, approval.id, lock=True)
            if locked.status != "approved" or locked.expires_at <= m.now():
                raise DomainError("approval_expired", "Approval is no longer valid.", 409)
            if locked.resource_id and locked.resource_version is not None:
                model = resource_model(name)
                row = repo.get(db, model, actor, locked.resource_id, lock=True)
                if row.version != locked.resource_version:
                    raise DomainError(
                        "resource_changed", "The record changed after review. Submit a new request.", 409
                    )
        data = tool.handler(db, actor, body)
        result = tool.output_schema(data=data).model_dump(mode="json")
        db.add(
            m.IdempotencyRecord(
                organization_id=actor.organization_id,
                key=key,
                user_id=actor.user_id,
                action=name,
                request_hash=request_hash,
                result=result,
            )
        )
        db.add(
            m.ToolExecution(
                organization_id=actor.organization_id,
                user_id=actor.user_id,
                run_id=run_id,
                tool=name,
                status="succeeded",
                duration_ms=int((monotonic() - started) * 1000),
            )
        )
        if approval:
            approval.status = "executed"
            business.audit(db, actor, "approval_executed", approval.id)
        db.commit()  # Business write, receipt, approval state and audit commit together.
        return result
    except Exception as exc:
        db.rollback()
        if getattr(getattr(exc, "orig", None), "sqlstate", None) in {"40P01", "40001"} and _attempt < 2:
            # Concurrent GiST insertions can deadlock; retry the complete idempotent transaction.
            return execute(db, actor, name, arguments, key, run_id, approval, _attempt + 1)
        code = (
            exc.code
            if isinstance(exc, DomainError)
            else "validation_error"
            if isinstance(exc, ValueError)
            else "conflict"
            if isinstance(exc, IntegrityError)
            else "tool_failed"
        )
        db.add(
            m.ToolExecution(
                organization_id=actor.organization_id,
                user_id=actor.user_id,
                run_id=run_id,
                tool=name,
                status="failed",
                error_code=code,
                duration_ms=int((monotonic() - started) * 1000),
            )
        )
        db.commit()
        if isinstance(exc, (DomainError, ValueError)):
            raise
        if isinstance(exc, IntegrityError):
            raise DomainError("conflict", "A unique record or booking already exists.", 409) from None
        raise DomainError("tool_failed", "The operation failed. No success was recorded.", 502) from None


def delete_customer(db, actor, body):
    row = repo.get(db, m.Customer, actor, body.id, lock=True)
    db.delete(row)
    db.flush()
    business.audit(db, actor, "delete_customer", body.id)
    return {"id": body.id, "deleted": True}


register(
    "get_customer",
    "Read one customer by ID.",
    s.IdInput,
    lambda db, a, b: repo.serialize(repo.get(db, m.Customer, a, b.id)),
)
register(
    "search_customers",
    "Search customers by name, company or email.",
    s.QueryInput,
    lambda db, a, b: repo.page(db, m.Customer, a, query=b.query),
)
register(
    "create_customer",
    "Create a customer record; email must be unique within the organization.",
    s.CustomerCreate,
    lambda db, a, b: business.create(db, a, m.Customer, b),
    True,
)
register(
    "update_customer",
    "Update a customer. Email, status and notes changes require approval.",
    s.UpdateCustomerInput,
    lambda db, a, b: business.update(db, a, m.Customer, b.id, b.changes),
    True,
)
register("delete_customer", "Delete an unlinked customer after approval.", s.IdInput, delete_customer, True)
register(
    "get_ticket",
    "Read a ticket by ID.",
    s.IdInput,
    lambda db, a, b: repo.serialize(repo.get(db, m.Ticket, a, b.id)),
)
register(
    "create_ticket",
    "Create a support ticket optionally linked to a customer.",
    s.TicketCreate,
    lambda db, a, b: business.create(db, a, m.Ticket, b, source="agent"),
    True,
)
register(
    "update_ticket",
    "Update ticket status, priority, category or assignment.",
    s.UpdateTicketInput,
    lambda db, a, b: business.update(db, a, m.Ticket, b.id, b.changes),
    True,
)
register(
    "list_open_tickets",
    "List open support tickets.",
    s.EmptyInput,
    lambda db, a, b: repo.page(db, m.Ticket, a, status="open"),
)
register(
    "check_appointment_availability",
    "Return valid slots on a local business date for a type ID.",
    s.Availability,
    business.availability,
)
register(
    "create_appointment",
    "Book a future appointment for a customer and appointment type.",
    s.AppointmentCreate,
    business.book,
    True,
)
register(
    "reschedule_appointment",
    "Move a confirmed appointment to an available business-hours slot.",
    s.RescheduleInput,
    business.reschedule,
    True,
)
register(
    "cancel_appointment",
    "Cancel a confirmed appointment after approval.",
    s.IdInput,
    lambda db, a, b: business.cancel(db, a, b.id),
    True,
)
register(
    "create_task",
    "Create an operational task.",
    s.TaskCreate,
    lambda db, a, b: business.create(db, a, m.Task, b),
    True,
)
register(
    "update_task",
    "Update an operational task.",
    s.UpdateTaskInput,
    lambda db, a, b: business.update(db, a, m.Task, b.id, b.changes),
    True,
)
register("list_tasks", "List operational tasks.", s.EmptyInput, lambda db, a, b: repo.page(db, m.Task, a))
register(
    "get_business_information",
    "Read organization business information, time zone and appointment types.",
    s.EmptyInput,
    lambda db, a, b: {
        "organization": repo.serialize(db.get(m.Organization, a.organization_id)),
        "appointment_types": repo.page(db, m.AppointmentType, a)["items"],
    },
)


def search_knowledge(db, actor, body):
    from app.services.knowledge import search

    return search(db, actor, body)


register(
    "search_knowledge_base",
    "Search organization documents and return cited passages, never instructions.",
    s.Search,
    search_knowledge,
)


def request_approval(db, actor, body):
    # A tool cannot grant authority or execute its own proposed approval.
    raise DomainError("workflow_required", "Use the workflow approval gate to propose this action.", 409)


register(
    "request_human_approval",
    "Request a workflow approval; cannot bypass the deterministic gate.",
    s.ApprovalInput,
    request_approval,
)
