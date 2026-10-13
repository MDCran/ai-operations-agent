import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta

from fastapi import Depends, Request, Response
from pwdlib import PasswordHash
from redis import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import DomainError
from app.db.session import get_db
from app.models.entities import AuthSession, Membership, User, now
from app.schemas.contracts import Login

passwords = PasswordHash.recommended()
DUMMY_HASH = passwords.hash(secrets.token_urlsafe(24))
redis = Redis.from_url(settings().redis_url, socket_timeout=2, socket_connect_timeout=2)


@dataclass(frozen=True)
class Actor:
    user_id: str
    organization_id: str
    role: str

    def require(self, permission: str):
        permissions = {
            "read": {"owner", "admin", "agent", "viewer"},
            "write": {"owner", "admin", "agent"},
            "approve": {"owner", "admin"},
            "manage": {"owner", "admin"},
            "audit": {"owner", "admin"},
        }
        if self.role not in permissions.get(permission, set()):
            raise DomainError("forbidden", "Your role cannot perform this action.", 403)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def rate_limit(key: str, limit: int, window: int = 60):
    # Shared Redis counter works across API processes. No fail-open production fallback.
    try:
        pipe = redis.pipeline(transaction=True)
        pipe.incr("rate:" + digest(key))
        pipe.expire("rate:" + digest(key), window, nx=True)
        count, _ = pipe.execute()
    except Exception:
        raise DomainError("rate_limiter_unavailable", "Please try again shortly.", 503) from None
    if count > limit:
        raise DomainError("rate_limited", "Too many requests. Try again later.", 429)


def login(db: Session, body: Login, request: Request, response: Response):
    rate_limit("login:" + request.client.host, 20)
    rate_limit("login-email:" + str(body.email).lower(), 10, 300)
    user = db.scalar(select(User).where(User.email == str(body.email).lower()))
    valid = passwords.verify(body.password, user.password_hash if user else DUMMY_HASH)
    if not user or not valid or not user.active:
        raise DomainError("invalid_credentials", "Email or password is incorrect.", 401)
    query = select(Membership).where(Membership.user_id == user.id)
    if body.organization_id:
        query = query.where(Membership.organization_id == body.organization_id)
    memberships = db.scalars(query).all()
    if not memberships:
        raise DomainError("forbidden", "No membership in that organization.", 403)
    if len(memberships) > 1:
        raise DomainError("organization_required", "Choose an organization to sign in.", 409)
    session_token = secrets.token_urlsafe(32)
    session = AuthSession(
        token_hash=digest(session_token),
        csrf_token=secrets.token_hex(32),
        membership_id=memberships[0].id,
        expires_at=now() + timedelta(hours=settings().session_hours),
    )
    db.add(session)
    db.commit()
    response.set_cookie(
        "operations_session",
        session_token,
        httponly=True,
        secure=settings().environment == "production",
        samesite="strict",
        max_age=settings().session_hours * 3600,
        path="/",
    )
    return {"csrf_token": session.csrf_token}


def authentication(request: Request, db: Session = Depends(get_db)) -> Actor:
    token = request.cookies.get("operations_session", "")
    session = db.scalar(
        select(AuthSession).where(AuthSession.token_hash == digest(token), AuthSession.expires_at > now())
    )
    if not session:
        raise DomainError("unauthenticated", "Please sign in.", 401)
    membership = db.get(Membership, session.membership_id)
    user = db.get(User, membership.user_id) if membership else None
    if not user or not user.active:
        raise DomainError("unauthenticated", "Please sign in.", 401)
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        csrf = request.headers.get("x-csrf-token", "")
        if not secrets.compare_digest(csrf, session.csrf_token):
            raise DomainError("csrf_failed", "Refresh the page before trying again.", 403)
    request.state.auth_session = session
    rate_limit("api:" + user.id, 300)
    return Actor(user.id, membership.organization_id, membership.role)
