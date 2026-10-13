from datetime import UTC, datetime
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now() -> datetime:
    return datetime.now(UTC)


def uid() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Identity:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Tenant:
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )


class Organization(Identity, Base):
    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(String(160))
    timezone: Mapped[str] = mapped_column(String(80), default="America/New_York")
    business_information: Mapped[str] = mapped_column(Text, default="")
    approval_tools: Mapped[list] = mapped_column(JSON, default=list)


class User(Identity, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Membership(Identity, Tenant, Base):
    __tablename__ = "organization_memberships"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id"),
        CheckConstraint("role IN ('owner','admin','agent','viewer')"),
    )


class AuthSession(Identity, Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    membership_id: Mapped[str] = mapped_column(ForeignKey("organization_memberships.id", ondelete="CASCADE"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Customer(Identity, Tenant, Base):
    __tablename__ = "customers"
    first_name: Mapped[str] = mapped_column(String(80))
    last_name: Mapped[str] = mapped_column(String(80), default="")
    email: Mapped[str] = mapped_column(String(254))
    phone: Mapped[str] = mapped_column(String(40), default="")
    company: Mapped[str] = mapped_column(String(160), default="")
    status: Mapped[str] = mapped_column(String(20), default="active")
    notes: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (
        UniqueConstraint("organization_id", "email"),
        UniqueConstraint("organization_id", "id"),
        CheckConstraint("status IN ('active','lead','inactive')"),
    )


class Ticket(Identity, Tenant, Base):
    __tablename__ = "tickets"
    version: Mapped[int] = mapped_column(Integer, default=1)
    customer_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(String(20), default="open")
    category: Mapped[str] = mapped_column(String(60), default="general")
    assigned_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="dashboard")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        ForeignKeyConstraint(
            ["organization_id", "customer_id"], ["customers.organization_id", "customers.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "assigned_user_id"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
        ),
        CheckConstraint("priority IN ('low','medium','high','urgent')"),
        CheckConstraint("status IN ('open','in_progress','pending','resolved','closed')"),
        Index("ix_tickets_tenant_status", "organization_id", "status"),
    )


class TicketComment(Identity, Tenant, Base):
    __tablename__ = "ticket_comments"
    ticket_id: Mapped[str] = mapped_column(String(36))
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "ticket_id"], ["tickets.organization_id", "tickets.id"], ondelete="CASCADE"
        ),
    )


class Task(Identity, Tenant, Base):
    __tablename__ = "tasks"
    version: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="todo")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (CheckConstraint("status IN ('todo','in_progress','done')"),)


class AppointmentType(Identity, Tenant, Base):
    __tablename__ = "appointment_types"
    name: Mapped[str] = mapped_column(String(100))
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30)
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "name"),
        CheckConstraint("duration_minutes >= 15 AND duration_minutes <= 240"),
    )


class BusinessHours(Identity, Tenant, Base):
    __tablename__ = "business_hours"
    weekday: Mapped[int] = mapped_column(Integer)
    open_minute: Mapped[int] = mapped_column(Integer, default=540)
    close_minute: Mapped[int] = mapped_column(Integer, default=1020)
    __table_args__ = (
        UniqueConstraint("organization_id", "weekday"),
        CheckConstraint("weekday BETWEEN 0 AND 6"),
        CheckConstraint("open_minute >= 0 AND close_minute <= 1440 AND close_minute > open_minute"),
    )


class Appointment(Identity, Tenant, Base):
    __tablename__ = "appointments"
    customer_id: Mapped[str] = mapped_column(String(36))
    appointment_type_id: Mapped[str] = mapped_column(String(36))
    title: Mapped[str] = mapped_column(String(200))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="confirmed")
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        ForeignKeyConstraint(
            ["organization_id", "customer_id"], ["customers.organization_id", "customers.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "appointment_type_id"],
            ["appointment_types.organization_id", "appointment_types.id"],
        ),
        CheckConstraint("ends_at > starts_at"),
        CheckConstraint("status IN ('confirmed','completed','cancelled')"),
        Index("ix_appointments_tenant_time", "organization_id", "starts_at"),
    )


class Conversation(Identity, Tenant, Base):
    __tablename__ = "conversations"
    title: Mapped[str] = mapped_column(String(160), default="New conversation")
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    __table_args__ = (UniqueConstraint("organization_id", "id"),)


class Message(Identity, Tenant, Base):
    __tablename__ = "messages"
    conversation_id: Mapped[str] = mapped_column(String(36))
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="complete")
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    citations: Mapped[list] = mapped_column(JSON, default=list)
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "conversation_id"],
            ["conversations.organization_id", "conversations.id"],
            ondelete="CASCADE",
        ),
    )


class AgentRun(Identity, Tenant, Base):
    __tablename__ = "agent_runs"
    conversation_id: Mapped[str] = mapped_column(String(36))
    requester_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(30), default="running")
    agent: Mapped[str] = mapped_column(String(30), default="supervisor")
    provider: Mapped[str] = mapped_column(String(30))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    outcome: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        ForeignKeyConstraint(
            ["organization_id", "conversation_id"], ["conversations.organization_id", "conversations.id"]
        ),
    )


class AgentStep(Identity, Tenant, Base):
    __tablename__ = "agent_steps"
    run_id: Mapped[str] = mapped_column(String(36))
    node: Mapped[str] = mapped_column(String(60))
    event: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "run_id"], ["agent_runs.organization_id", "agent_runs.id"], ondelete="CASCADE"
        ),
    )


class ToolExecution(Identity, Tenant, Base):
    __tablename__ = "tool_executions"
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    tool: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30))
    duration_ms: Mapped[int] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)


class Approval(Identity, Tenant, Base):
    __tablename__ = "approval_requests"
    run_id: Mapped[str] = mapped_column(String(36), unique=True)
    requester_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    decided_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict] = mapped_column(JSON)
    payload_hash: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    resource_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "run_id"], ["agent_runs.organization_id", "agent_runs.id"]),
    )


class Document(Identity, Tenant, Base):
    __tablename__ = "documents"
    name: Mapped[str] = mapped_column(String(200))
    storage_key: Mapped[str] = mapped_column(String(80))
    size_bytes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="queued")
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    embedding_provider: Mapped[str] = mapped_column(String(30))
    embedding_model: Mapped[str] = mapped_column(String(80))
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (UniqueConstraint("organization_id", "id"),)


class DocumentChunk(Identity, Tenant, Base):
    __tablename__ = "document_chunks"
    document_id: Mapped[str] = mapped_column(String(36))
    ordinal: Mapped[int] = mapped_column(Integer)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list] = mapped_column(Vector(1536))
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "document_id"],
            ["documents.organization_id", "documents.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("document_id", "ordinal"),
        Index(
            "ix_chunks_vector",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class AuditLog(Identity, Tenant, Base):
    __tablename__ = "audit_logs"
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    changed_fields: Mapped[list] = mapped_column(JSON, default=list)
    __table_args__ = (Index("ix_audit_tenant_created", "organization_id", "created_at"),)


class IdempotencyRecord(Identity, Tenant, Base):
    __tablename__ = "idempotency_records"
    key: Mapped[str] = mapped_column(String(160))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80))
    request_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("organization_id", "key"),)
