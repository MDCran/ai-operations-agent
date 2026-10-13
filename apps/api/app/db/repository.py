from datetime import datetime

from sqlalchemy import func, inspect, or_, select
from sqlalchemy.orm import Session

from app.auth.security import Actor
from app.core.errors import DomainError


def serialize(entity) -> dict:
    result = {}
    for column in inspect(entity).mapper.column_attrs:
        if column.key in {"password_hash", "token_hash", "csrf_token", "embedding", "storage_key"}:
            continue
        value = getattr(entity, column.key)
        result[column.key] = value.isoformat() if isinstance(value, datetime) else value
    return result


def get(db: Session, model, actor: Actor, resource_id: str, lock=False):
    query = select(model).where(model.organization_id == actor.organization_id, model.id == resource_id)
    if lock:
        query = query.with_for_update()
    row = db.scalar(query)
    if not row:
        raise DomainError("not_found", "Record not found.", 404)
    return row


def page(
    db: Session,
    model,
    actor: Actor,
    offset=0,
    limit=25,
    query="",
    status=None,
    sort="created_at",
    descending=True,
):
    stmt = select(model).where(model.organization_id == actor.organization_id)
    fields = [
        getattr(model, name)
        for name in ("title", "name", "first_name", "last_name", "email", "company")
        if hasattr(model, name)
    ]
    if query and fields:
        # Escape LIKE wildcards so user input has literal search semantics.
        pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        stmt = stmt.where(or_(*[field.ilike(pattern, escape="\\") for field in fields]))
    if status and hasattr(model, "status"):
        stmt = stmt.where(model.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    allowed = {"created_at", "updated_at", "title", "first_name", "starts_at", "status"}
    field = getattr(model, sort if sort in allowed and hasattr(model, sort) else "created_at")
    rows = db.scalars(
        stmt.order_by(field.desc() if descending else field.asc(), model.id).offset(offset).limit(limit)
    ).all()
    return {"items": [serialize(row) for row in rows], "total": total, "offset": offset, "limit": limit}
