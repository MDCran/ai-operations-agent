from sqlalchemy import select, text

from app.core.config import settings
from app.core.errors import DomainError
from app.models import entities as m
from app.tools.registry import execute, requires_approval


def start_run(db, actor, conversation_id, message, request_id):
    from app.db import repository as repo

    actor.require("write")
    conversation = repo.get(db, m.Conversation, actor, conversation_id)
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 2))"),
        {"key": actor.organization_id + request_id},
    )
    prior = db.scalar(
        select(m.IdempotencyRecord).where(
            m.IdempotencyRecord.organization_id == actor.organization_id,
            m.IdempotencyRecord.key == "chat:" + request_id,
        )
    )
    from app.tools.registry import payload_hash

    hashed = payload_hash("chat", {"conversation_id": conversation_id, "message": message})
    if prior:
        if prior.request_hash != hashed or prior.user_id != actor.user_id:
            raise DomainError("idempotency_conflict", "Request key was already used.", 409)
        return db.get(m.AgentRun, prior.result["run_id"])
    run = m.AgentRun(
        organization_id=actor.organization_id,
        requester_id=actor.user_id,
        conversation_id=conversation.id,
        provider=settings().ai_provider,
    )
    db.add(run)
    db.flush()
    db.add(
        m.Message(
            organization_id=actor.organization_id,
            conversation_id=conversation.id,
            role="user",
            content=message,
            run_id=run.id,
        )
    )
    db.add(
        m.IdempotencyRecord(
            organization_id=actor.organization_id,
            key="chat:" + request_id,
            user_id=actor.user_id,
            action="chat",
            request_hash=hashed,
            result={"run_id": run.id},
        )
    )
    if conversation.title == "New conversation":
        conversation.title = message[:80]
    db.commit()
    return run


def dispatch(db, actor, name, arguments, key):
    if requires_approval(db, actor, name, arguments):
        from app.workflows.engine import drive

        actor.require("write")
        # Stable dedicated conversation per API proposal is encoded in its idempotency receipt.
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 3))"),
            {"key": actor.organization_id + key},
        )
        prior = db.scalar(
            select(m.IdempotencyRecord).where(
                m.IdempotencyRecord.organization_id == actor.organization_id,
                m.IdempotencyRecord.key == "proposal:" + key,
            )
        )
        from app.tools.registry import payload_hash

        hashed = payload_hash(name, arguments)
        if prior:
            if prior.request_hash != hashed or prior.user_id != actor.user_id:
                raise DomainError("idempotency_conflict", "Request key was already used.", 409)
            return prior.result
        conversation = m.Conversation(
            organization_id=actor.organization_id, user_id=actor.user_id, title="Approval: " + name
        )
        db.add(conversation)
        db.flush()
        # Structured proposals bypass language interpretation; OpenAI mode must preserve exact reviewed action.
        run = m.AgentRun(
            organization_id=actor.organization_id,
            requester_id=actor.user_id,
            conversation_id=conversation.id,
            provider=settings().ai_provider,
            agent="scheduling" if "appointment" in name else "operations",
        )
        db.add(run)
        db.flush()
        response = {"status": "pending_approval", "run_id": run.id}
        db.add(
            m.IdempotencyRecord(
                organization_id=actor.organization_id,
                key="proposal:" + key,
                user_id=actor.user_id,
                action=name,
                request_hash=hashed,
                result=response,
            )
        )
        db.commit()
        plan = {
            "agent": run.agent,
            "reason": "Dashboard requested a protected change.",
            "calls": [{"name": name, "arguments": arguments}],
        }
        # Preload through a supported input field; the supervisor validates the supplied typed plan.
        list(drive(run.id, proposed_plan=plan))
        return response
    return execute(db, actor, name, arguments, key="http:" + key)["data"]
