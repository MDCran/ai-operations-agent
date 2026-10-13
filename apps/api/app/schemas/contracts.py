from datetime import date, datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Login(StrictModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)
    organization_id: str | None = None


class CustomerCreate(StrictModel):
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(default="", max_length=80)
    email: EmailStr
    phone: str = Field(default="", max_length=40)
    company: str = Field(default="", max_length=160)
    status: Literal["active", "lead", "inactive"] = "active"
    notes: str = Field(default="", max_length=10000)
    tags: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        return str(value).lower()


class CustomerPatch(StrictModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=80)
    last_name: str | None = Field(default=None, max_length=80)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    company: str | None = Field(default=None, max_length=160)
    status: Literal["active", "lead", "inactive"] | None = None
    notes: str | None = Field(default=None, max_length=10000)
    tags: list[str] | None = Field(default=None, max_length=20)


class TicketCreate(StrictModel):
    customer_id: str | None = None
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10000)
    priority: Literal["low", "medium", "high", "urgent"] = "medium"
    category: str = Field(default="general", max_length=60)


class TicketPatch(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    priority: Literal["low", "medium", "high", "urgent"] | None = None
    status: Literal["open", "in_progress", "pending", "resolved", "closed"] | None = None
    category: str | None = Field(default=None, max_length=60)
    assigned_user_id: str | None = None


class CommentCreate(StrictModel):
    body: str = Field(min_length=1, max_length=5000)


class TaskCreate(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10000)
    due_at: datetime | None = None

    @field_validator("due_at")
    @classmethod
    def due_date_is_aware(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("Use a timezone-aware timestamp")
        return value


class TaskPatch(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    status: Literal["todo", "in_progress", "done"] | None = None
    due_at: datetime | None = None

    @field_validator("due_at")
    @classmethod
    def due_date_is_aware(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("Use a timezone-aware timestamp")
        return value


class AppointmentTypeCreate(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    duration_minutes: int = Field(ge=15, le=240)


class AppointmentTypePatch(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    duration_minutes: int | None = Field(default=None, ge=15, le=240)


class Availability(StrictModel):
    date: date
    appointment_type_id: str


class AppointmentCreate(StrictModel):
    customer_id: str
    appointment_type_id: str
    title: str = Field(min_length=1, max_length=200)
    starts_at: datetime

    @field_validator("starts_at")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("Use a timezone-aware timestamp")
        return value


class AppointmentMove(StrictModel):
    starts_at: datetime

    _aware = field_validator("starts_at")(AppointmentCreate.aware.__func__)


class Search(StrictModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)
    threshold: float = Field(default=0.15, ge=0, le=1)
    document_id: str | None = None


class Chat(StrictModel):
    conversation_id: str
    message: str = Field(min_length=1, max_length=8000)
    request_id: str = Field(min_length=8, max_length=100)


class ToolCall(StrictModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class Plan(StrictModel):
    agent: Literal["knowledge", "support", "scheduling", "operations"]
    reason: str
    calls: list[ToolCall] = Field(default_factory=list, max_length=5)


class Answer(StrictModel):
    text: str
    citation_ids: list[str] = Field(default_factory=list)


class ToolResult(StrictModel):
    data: dict[str, Any] = Field(default_factory=dict)


class IdInput(StrictModel):
    id: str


class QueryInput(StrictModel):
    query: str = Field(default="", max_length=200)


class EmptyInput(StrictModel):
    pass


class UpdateCustomerInput(StrictModel):
    id: str
    changes: CustomerPatch


class UpdateTicketInput(StrictModel):
    id: str
    changes: TicketPatch


class UpdateTaskInput(StrictModel):
    id: str
    changes: TaskPatch


class RescheduleInput(StrictModel):
    id: str
    starts_at: datetime

    _aware = field_validator("starts_at")(AppointmentCreate.aware.__func__)


class ApprovalInput(StrictModel):
    action: str
    arguments: dict[str, Any]
    reason: str = Field(min_length=1, max_length=1000)


class OrganizationPatch(StrictModel):
    name: str = Field(min_length=1, max_length=160)
    timezone: str
    business_information: str = Field(max_length=10000)
    approval_tools: list[str] = Field(default_factory=list)

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, value):
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError:
            raise ValueError("Unknown IANA time zone") from None
        return value


class HoursInput(StrictModel):
    weekday: int = Field(ge=0, le=6)
    open_minute: int = Field(ge=0, le=1439)
    close_minute: int = Field(ge=1, le=1440)


class HoursUpdate(StrictModel):
    hours: list[HoursInput] = Field(max_length=7)


class MemberCreate(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=12, max_length=200)
    role: Literal["admin", "agent", "viewer"]


class RolePatch(StrictModel):
    role: Literal["admin", "agent", "viewer"]
