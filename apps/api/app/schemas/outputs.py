"""Response schemas derived from the public database contract; secret/storage fields are excluded."""

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, create_model
from sqlalchemy import JSON, Boolean, DateTime, Float, Integer

from app.models import entities as m


class PublicModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def entity_schema(model):
    fields = {}
    for column in model.__table__.columns:
        if column.name in {"password_hash", "token_hash", "csrf_token", "storage_key", "embedding"}:
            continue
        field_type = (
            datetime
            if isinstance(column.type, DateTime)
            else bool
            if isinstance(column.type, Boolean)
            else int
            if isinstance(column.type, Integer)
            else float
            if isinstance(column.type, Float)
            else list[str]
            if column.name in {"tags", "changed_fields", "approval_tools"}
            else Any
            if isinstance(column.type, JSON)
            else str
        )
        if column.nullable:
            field_type = field_type | None
        fields[column.name] = (field_type, ...)
    return create_model(model.__name__ + "Response", __base__=PublicModel, **fields)


T = TypeVar("T")


class Paginated(PublicModel, Generic[T]):
    items: list[T]
    total: int
    offset: int
    limit: int


CustomerResponse = entity_schema(m.Customer)
TicketResponse = entity_schema(m.Ticket)
TaskResponse = entity_schema(m.Task)
AppointmentResponse = entity_schema(m.Appointment)
AppointmentTypeResponse = entity_schema(m.AppointmentType)
ConversationResponse = entity_schema(m.Conversation)
DocumentResponse = entity_schema(m.Document)
ApprovalResponse = entity_schema(m.Approval)
RunResponse = entity_schema(m.AgentRun)
AuditResponse = entity_schema(m.AuditLog)


class Hit(PublicModel):
    chunk_id: str
    document_id: str
    document_name: str
    page: int | None
    content: str
    score: float


class SearchResponse(PublicModel):
    hits: list[Hit]
    debug: dict[str, Any]


class Slot(PublicModel):
    starts_at: datetime
    ends_at: datetime


class AvailabilityResponse(PublicModel):
    slots: list[Slot]
    timezone: str
    duration_minutes: int


class ApprovalPending(PublicModel):
    status: str
    run_id: str


TOOL_OUTPUTS = {
    "get_customer": CustomerResponse,
    "search_customers": Paginated[CustomerResponse],
    "create_customer": CustomerResponse,
    "update_customer": CustomerResponse,
    "get_ticket": TicketResponse,
    "create_ticket": TicketResponse,
    "update_ticket": TicketResponse,
    "list_open_tickets": Paginated[TicketResponse],
    "create_task": TaskResponse,
    "update_task": TaskResponse,
    "list_tasks": Paginated[TaskResponse],
    "create_appointment": AppointmentResponse,
    "reschedule_appointment": AppointmentResponse,
    "cancel_appointment": AppointmentResponse,
    "check_appointment_availability": AvailabilityResponse,
    "search_knowledge_base": SearchResponse,
}
