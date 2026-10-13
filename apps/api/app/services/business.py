from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import Actor
from app.core.errors import DomainError
from app.db import repository as repo
from app.models import entities as m
from app.schemas import contracts as s


def audit(db: Session, actor: Actor, action: str, resource_id: str | None, fields=()):
    db.add(
        m.AuditLog(
            organization_id=actor.organization_id,
            actor_id=actor.user_id,
            action=action,
            resource_id=resource_id,
            changed_fields=list(fields),
        )
    )


def create(db: Session, actor: Actor, model, body, **extra):
    actor.require("write")
    values = body.model_dump(mode="python")
    values.update(extra)
    if values.get("customer_id"):
        repo.get(db, m.Customer, actor, values["customer_id"])
    row = model(organization_id=actor.organization_id, **values)
    db.add(row)
    db.flush()
    audit(db, actor, "create_" + model.__tablename__, row.id, values.keys())
    return repo.serialize(row)


def update(db: Session, actor: Actor, model, resource_id: str, changes):
    actor.require("write")
    row = repo.get(db, model, actor, resource_id, lock=True)
    values = changes.model_dump(exclude_unset=True)
    nullable = {"assigned_user_id", "due_at"}
    if any(value is None and key not in nullable for key, value in values.items()):
        raise DomainError("invalid_input", "This field cannot be null.")
    if values.get("assigned_user_id") and not db.scalar(
        select(m.Membership).where(
            m.Membership.organization_id == actor.organization_id,
            m.Membership.user_id == values["assigned_user_id"],
        )
    ):
        raise DomainError("not_found", "Team member not found.", 404)
    if values.get("email"):
        values["email"] = str(values["email"]).lower()
    for key, value in values.items():
        setattr(row, key, value)
    if hasattr(row, "version"):
        row.version += 1
    if model is m.Ticket and "status" in values:
        row.resolved_at = m.now() if row.status in {"resolved", "closed"} else None
    db.flush()
    audit(db, actor, "update_" + model.__tablename__, row.id, values.keys())
    return repo.serialize(row)


def booking_window(db: Session, actor: Actor, starts_at: datetime, type_id: str):
    appointment_type = repo.get(db, m.AppointmentType, actor, type_id)
    organization = db.get(m.Organization, actor.organization_id)
    start = starts_at.astimezone(UTC)
    end = start + timedelta(minutes=appointment_type.duration_minutes)
    local_start = start.astimezone(ZoneInfo(organization.timezone))
    local_end = end.astimezone(ZoneInfo(organization.timezone))
    hours = db.scalar(
        select(m.BusinessHours).where(
            m.BusinessHours.organization_id == actor.organization_id,
            m.BusinessHours.weekday == local_start.weekday(),
        )
    )
    minute = local_start.hour * 60 + local_start.minute
    end_minute = local_end.hour * 60 + local_end.minute
    if start < m.now():
        raise DomainError("past_appointment", "Choose a future appointment time.")
    if (
        not hours
        or local_start.date() != local_end.date()
        or minute < hours.open_minute
        or end_minute > hours.close_minute
        or local_start.second
        or local_start.microsecond
    ):
        raise DomainError("outside_business_hours", "That time is outside business hours.")
    return start, end


def availability(db: Session, actor: Actor, body: s.Availability):
    org = db.get(m.Organization, actor.organization_id)
    zone = ZoneInfo(org.timezone)
    appointment_type = repo.get(db, m.AppointmentType, actor, body.appointment_type_id)
    hours = db.scalar(
        select(m.BusinessHours).where(
            m.BusinessHours.organization_id == actor.organization_id,
            m.BusinessHours.weekday == body.date.weekday(),
        )
    )
    slots = []
    if hours:
        day_start = datetime.combine(body.date, time(), zone)
        booked = db.scalars(
            select(m.Appointment).where(
                m.Appointment.organization_id == actor.organization_id,
                m.Appointment.status == "confirmed",
                m.Appointment.starts_at < day_start + timedelta(days=1),
                m.Appointment.ends_at > day_start,
            )
        ).all()
        for minute in range(
            hours.open_minute, hours.close_minute - appointment_type.duration_minutes + 1, 15
        ):
            local = day_start + timedelta(minutes=minute)
            start = local.astimezone(UTC)
            end = start + timedelta(minutes=appointment_type.duration_minutes)
            # UTC round-trip rejects nonexistent local times on DST transitions.
            if start.astimezone(zone).replace(tzinfo=None) != local.replace(tzinfo=None):
                continue
            if start <= m.now() or any(start < b.ends_at and end > b.starts_at for b in booked):
                continue
            try:
                booking_window(db, actor, start, appointment_type.id)
            except DomainError:
                continue
            slots.append({"starts_at": start.isoformat(), "ends_at": end.isoformat()})
    return {"slots": slots, "timezone": org.timezone, "duration_minutes": appointment_type.duration_minutes}


def book(db: Session, actor: Actor, body: s.AppointmentCreate):
    actor.require("write")
    repo.get(db, m.Customer, actor, body.customer_id)
    start, end = booking_window(db, actor, body.starts_at, body.appointment_type_id)
    return create(db, actor, m.Appointment, body, starts_at=start, ends_at=end)


def reschedule(db: Session, actor: Actor, body: s.RescheduleInput):
    actor.require("write")
    row = repo.get(db, m.Appointment, actor, body.id, lock=True)
    if row.status != "confirmed":
        raise DomainError("invalid_status", "Only confirmed appointments can be rescheduled.", 409)
    row.starts_at, row.ends_at = booking_window(db, actor, body.starts_at, row.appointment_type_id)
    row.version += 1
    db.flush()  # PostgreSQL exclusion constraint is the final conflict authority.
    audit(db, actor, "reschedule_appointment", row.id, ["starts_at", "ends_at"])
    return repo.serialize(row)


def cancel(db: Session, actor: Actor, resource_id: str):
    actor.require("write")
    row = repo.get(db, m.Appointment, actor, resource_id, lock=True)
    if row.status != "confirmed":
        raise DomainError("invalid_status", "Appointment is no longer confirmed.", 409)
    row.status = "cancelled"
    row.version += 1
    db.flush()
    audit(db, actor, "cancel_appointment", row.id, ["status"])
    return repo.serialize(row)
