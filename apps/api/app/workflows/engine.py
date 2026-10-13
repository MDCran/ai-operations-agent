from contextlib import contextmanager
from datetime import timedelta
from time import monotonic
from typing import TypedDict

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from sqlalchemy import select, text

from app.agents.providers import provider
from app.auth.security import Actor
from app.core.config import settings
from app.core.errors import DomainError
from app.db import repository as repo
from app.db.session import SessionLocal
from app.models import entities as m
from app.schemas import contracts as s
from app.services.business import audit
from app.tools.registry import REGISTRY, execute, payload_hash, requires_approval, resource_model


class State(TypedDict, total=False):
    run_id: str
    message: str
    plan: dict
    results: list[dict]
    answer: dict
    approved: bool
    approval_id: str | None
    proposed_plan: dict | None


ALLOWED = {
    "knowledge": {"search_knowledge_base", "get_business_information"},
    "support": {
        "search_knowledge_base",
        "get_customer",
        "search_customers",
        "get_ticket",
        "create_ticket",
        "update_ticket",
        "list_open_tickets",
        "get_business_information",
    },
    "scheduling": {
        "search_customers",
        "get_customer",
        "get_business_information",
        "check_appointment_availability",
        "create_appointment",
        "reschedule_appointment",
        "cancel_appointment",
    },
    "operations": {
        "get_customer",
        "search_customers",
        "create_customer",
        "update_customer",
        "delete_customer",
        "list_tasks",
        "create_task",
        "update_task",
        "get_business_information",
        "request_human_approval",
    },
}


def actor_for(db, run):
    member = db.scalar(
        select(m.Membership).where(
            m.Membership.user_id == run.requester_id, m.Membership.organization_id == run.organization_id
        )
    )
    user = db.get(m.User, run.requester_id)
    if not member or not user or not user.active:
        raise DomainError("permission_revoked", "The requester no longer has access.", 403)
    return Actor(member.user_id, member.organization_id, member.role)


def add_usage(run, usage):
    run.input_tokens += usage.get("input_tokens", 0)
    run.output_tokens += usage.get("output_tokens", 0)


def supervisor(state: State):
    with SessionLocal() as db:
        run = db.get(m.AgentRun, state["run_id"])
        actor = actor_for(db, run)
        actor.require("write")
        history = db.scalars(
            select(m.Message)
            .where(
                m.Message.conversation_id == run.conversation_id,
                m.Message.organization_id == actor.organization_id,
            )
            .order_by(m.Message.created_at.desc())
            .limit(12)
        ).all()
        context = [{"role": row.role, "content": row.content[:1500]} for row in reversed(history)]
        tools = [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema.model_json_schema()}
            for t in REGISTRY.values()
        ]
        if state.get("proposed_plan"):
            plan, usage = s.Plan.model_validate(state["proposed_plan"]), {}
        else:
            plan, usage = provider().plan(state["message"], context, tools)
        if any(call.name not in ALLOWED[plan.agent] for call in plan.calls):
            raise DomainError("invalid_route", "The proposed tool does not belong to this agent.")
        if any(call.name == "request_human_approval" for call in plan.calls):
            if len(plan.calls) != 1:
                raise DomainError("invalid_plan", "An approval proposal must be a single action.")
            proposal = s.ApprovalInput.model_validate(plan.calls[0].arguments)
            if (
                proposal.action not in ALLOWED["operations"]
                or proposal.action == "request_human_approval"
                or not REGISTRY[proposal.action].writes
            ):
                raise DomainError("invalid_plan", "Only authorized business writes can be proposed.")
            plan.calls = [s.ToolCall(name=proposal.action, arguments=proposal.arguments)]
            plan.reason = proposal.reason
        for call in plan.calls:
            call.arguments = (
                REGISTRY[call.name]
                .input_schema.model_validate(call.arguments)
                .model_dump(mode="json", exclude_unset=True)
            )
        protected = [
            c
            for c in plan.calls
            if REGISTRY[c.name].writes and requires_approval(db, actor, c.name, c.arguments)
        ]
        if protected and len(plan.calls) != 1:
            raise DomainError("single_approval_action", "Submit each protected change in its own request.")
        run.agent = plan.agent
        add_usage(run, usage)
        db.commit()
        return {"plan": plan.model_dump(mode="json"), "results": [], "approval_id": None}


def specialist(state: State):
    # Separate observable nodes establish responsibility; tools enforce authorization independently.
    return {"plan": state["plan"]}


def approval_gate(state: State):
    plan = s.Plan.model_validate(state["plan"])
    with SessionLocal() as db:
        run = db.get(m.AgentRun, state["run_id"])
        actor = actor_for(db, run)
        protected = [
            c
            for c in plan.calls
            if REGISTRY[c.name].writes and requires_approval(db, actor, c.name, c.arguments)
        ]
        request = db.scalar(select(m.Approval).where(m.Approval.run_id == run.id))
        if not protected and not request:
            return {"approved": True}
        call = protected[0] if protected else plan.calls[0]
        if not request:
            resource_id = call.arguments.get("id")
            version = None
            if resource_id:
                model = resource_model(call.name)
                version = repo.get(db, model, actor, resource_id).version
            request = m.Approval(
                organization_id=actor.organization_id,
                run_id=run.id,
                requester_id=actor.user_id,
                action=call.name,
                payload=call.arguments,
                payload_hash=payload_hash(call.name, call.arguments),
                resource_id=resource_id,
                resource_version=version,
                reason=plan.reason,
                expires_at=m.now() + timedelta(hours=24),
            )
            db.add(request)
            db.flush()
            audit(db, actor, "approval_requested", request.id)
        run.status = "pending_approval"
        db.commit()
        approval_id = request.id
    # Never perform a write after receiving a decision without checking the persisted decision.
    interrupt({"approval_id": approval_id, "action": call.name})
    with SessionLocal() as db:
        request = db.get(m.Approval, approval_id)
        approved = request.status in {"approved", "executed"} and request.expires_at > m.now()
    return {"approved": approved, "approval_id": approval_id}


def execute_tools(state: State):
    results = []
    with SessionLocal() as db:
        run = db.get(m.AgentRun, state["run_id"])
        actor = actor_for(db, run)
        approval = db.get(m.Approval, state["approval_id"]) if state.get("approval_id") else None
        for index, call in enumerate(s.Plan.model_validate(state["plan"]).calls):
            result = execute(
                db,
                actor,
                call.name,
                call.arguments,
                key=f"run:{run.id}:{index}",
                run_id=run.id,
                approval=approval,
            )
            results.append(result)
        # Deterministic customer inquiry fallback; no fabricated resolution or duplicate ticket.
        if (
            state["plan"]["agent"] == "support"
            and results
            and all("hits" in r["data"] for r in results)
            and not any(r["data"]["hits"] for r in results)
        ):
            results.append(
                execute(
                    db,
                    actor,
                    "create_ticket",
                    {
                        "title": state["message"][:200],
                        "description": state["message"],
                        "category": "knowledge_gap",
                    },
                    key=f"run:{run.id}:fallback",
                    run_id=run.id,
                )
            )
    return {"results": results}


def final_answer(state: State):
    if not state.get("approved", True):
        answer = s.Answer(text="The request was rejected or expired. No proposed action was executed.")
        usage = {}
    elif not state["plan"]["calls"]:
        answer = s.Answer(text=state["plan"]["reason"])
        usage = {}
    else:
        answer, usage = provider().answer(state["message"], state.get("results", []))
    evidence = {
        hit["chunk_id"]: hit for result in state.get("results", []) for hit in result["data"].get("hits", [])
    }
    if any(cid not in evidence for cid in answer.citation_ids):
        raise DomainError(
            "invalid_citations", "The model returned a source outside the retrieved evidence.", 502
        )
    if evidence and not answer.citation_ids:
        answer = s.Answer(
            text="Retrieved evidence is available, but the model did not provide verifiable citations. "
            "Inspect the sources or rephrase your question.",
            citation_ids=list(evidence),
        )
    with SessionLocal() as db:
        run = db.get(m.AgentRun, state["run_id"])
        add_usage(run, usage)
        db.commit()
    return {"answer": {"text": answer.text, "citations": [evidence[c] for c in answer.citation_ids]}}


@contextmanager
def graph_context():
    with PostgresSaver.from_conn_string(settings().postgres_dsn) as saver:
        graph = StateGraph(State)
        graph.add_node("supervisor", supervisor)
        for agent in ALLOWED:
            graph.add_node(agent, specialist)
            graph.add_edge(agent, "approval_gate")
        graph.add_node("approval_gate", approval_gate)
        graph.add_node("execute_tools", execute_tools)
        graph.add_node("final_answer", final_answer)
        graph.add_edge(START, "supervisor")
        graph.add_conditional_edges("supervisor", lambda state: state["plan"]["agent"])
        graph.add_conditional_edges(
            "approval_gate", lambda state: "execute_tools" if state["approved"] else "final_answer"
        )
        graph.add_edge("execute_tools", "final_answer")
        graph.add_edge("final_answer", END)
        yield graph.compile(checkpointer=saver)


def drive(run_id: str, message: str | None = None, resume=False, proposed_plan=None):
    started = monotonic()
    # Session-level advisory lock spans DB transactions AND graph checkpoints, preventing concurrent resumes.
    from app.db.session import engine

    with engine.connect() as lock:
        acquired = lock.scalar(
            text("SELECT pg_try_advisory_lock(hashtextextended(:key, 1))"), {"key": run_id}
        )
        lock.commit()
        if not acquired:
            return
        try:
            with SessionLocal() as db:
                run = db.get(m.AgentRun, run_id)
                if not run or run.status in {"succeeded", "rejected"}:
                    return
            with graph_context() as graph:
                config = {"configurable": {"thread_id": run_id}, "recursion_limit": 20}
                checkpoint = graph.get_state(config)
                if resume:
                    input_value = (
                        Command(resume=True)
                        if checkpoint.tasks and any(task.interrupts for task in checkpoint.tasks)
                        else None
                    )
                else:
                    input_value = (
                        {"run_id": run_id, "message": message or "", "proposed_plan": proposed_plan}
                        if not checkpoint.values
                        else None
                    )
                for event in graph.stream(input_value, config, stream_mode="updates"):
                    for node, data in event.items():
                        if node == "__interrupt__":
                            yield {"type": "approval", "data": data[0].value}
                            return
                        with SessionLocal() as db:
                            run = db.get(m.AgentRun, run_id)
                            db.add(
                                m.AgentStep(
                                    organization_id=run.organization_id,
                                    run_id=run_id,
                                    node=node,
                                    event={"completed": True},
                                )
                            )
                            db.commit()
                        yield {"type": "step", "data": {"node": node, "run_id": run_id}}
                state = graph.get_state(config).values
                answer = state["answer"]
                with SessionLocal() as db:
                    run = db.get(m.AgentRun, run_id)
                    actor = actor_for(db, run)
                    # Lock + final-state guard prevent duplicate final messages on worker recovery.
                    if run.status not in {"succeeded", "rejected"}:
                        run.status = "succeeded" if state.get("approved", True) else "rejected"
                        run.outcome = answer
                        run.duration_ms += int((monotonic() - started) * 1000)
                        db.add(
                            m.Message(
                                organization_id=actor.organization_id,
                                conversation_id=run.conversation_id,
                                role="assistant",
                                content=answer["text"],
                                citations=answer["citations"],
                                run_id=run.id,
                            )
                        )
                        db.commit()
                yield {"type": "answer", "data": answer}
        except Exception as exc:
            code = exc.code if isinstance(exc, DomainError) else "workflow_failed"
            with SessionLocal() as db:
                run = db.get(m.AgentRun, run_id)
                run.status = "failed"
                run.error_code = code
                run.duration_ms += int((monotonic() - started) * 1000)
                db.commit()
            yield {
                "type": "error",
                "data": {"code": code, "message": "The workflow failed. Inspect the run details."},
            }
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(hashtextextended(:key, 1))"), {"key": run_id})
            lock.commit()
