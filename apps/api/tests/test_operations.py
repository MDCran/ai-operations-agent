from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.security import Actor
from app.core.errors import DomainError
from app.db.session import SessionLocal
from app.main import app
from app.models import entities as m
from app.schemas import contracts as s
from app.services.knowledge import ingest
from app.tools.registry import execute
from app.workflows.engine import drive


def test_auth_csrf_and_logout(client):
    with TestClient(app) as unauth:
        assert unauth.get("/api/v1/customers").status_code == 401
    old = client.headers.pop("X-CSRF-Token")
    assert (
        client.post(
            "/api/v1/tasks", json={"title": "Blocked"}, headers={"Idempotency-Key": str(uuid4())}
        ).status_code
        == 403
    )
    client.headers["X-CSRF-Token"] = old
    assert client.post("/api/v1/auth/logout").status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


def test_reject_untrusted_origin(client, key):
    result = client.post(
        "/api/v1/tasks", json={"title": "Blocked"}, headers={**key, "Origin": "https://evil.example"}
    )
    assert result.status_code == 403


def test_password_not_echoed(client):
    result = client.post("/api/v1/auth/login", json={"email": "invalid", "password": "secret-never-echo"})
    assert result.status_code == 422
    assert "secret-never-echo" not in result.text


def test_idempotent_write_and_conflict(client, key):
    body = {"title": "Follow up"}
    first = client.post("/api/v1/tasks", json=body, headers=key)
    repeated = client.post("/api/v1/tasks", json=body, headers=key)
    assert first.json()["id"] == repeated.json()["id"]
    assert client.get("/api/v1/tasks").json()["total"] == 1
    conflict = client.post("/api/v1/tasks", json={"title": "Different"}, headers=key)
    assert conflict.status_code == 409


def test_tenant_scoping_and_fk(client, customer, tenant):
    with SessionLocal() as db:
        other = m.Organization(name="Other tenant")
        db.add(other)
        db.flush()
        foreign = m.Customer(organization_id=other.id, first_name="Hidden", email="hidden@example.com")
        db.add(foreign)
        db.commit()
        foreign_id = foreign.id
        assert client.get(f"/api/v1/customers/{foreign_id}").status_code == 404
        assert (
            client.post(
                "/api/v1/tickets",
                json={"title": "Test", "customer_id": foreign_id},
                headers={"Idempotency-Key": str(uuid4())},
            ).status_code
            == 404
        )
        assert client.get("/api/v1/customers").json()["total"] == 1
        assert client.get("/api/v1/dashboard/summary").json()["customers"] == 1
        db.delete(other)
        db.commit()


def test_viewer_cannot_write_tools_or_http(client, tenant, key):
    with SessionLocal() as db:
        member = db.scalar(select(m.Membership).where(m.Membership.user_id == tenant["user"]))
        member.role = "viewer"
        db.commit()
    assert client.post("/api/v1/tasks", json={"title": "Blocked"}, headers=key).status_code == 403
    assert client.get("/api/v1/tasks").status_code == 200
    assert client.get("/api/v1/audit-logs").status_code == 403
    with SessionLocal() as db:
        with pytest.raises(DomainError, match="cannot perform"):
            execute(
                db,
                Actor(tenant["user"], tenant["org"], "viewer"),
                "create_task",
                {"title": "Blocked"},
                str(uuid4()),
            )


def test_ticket_comments_assignment_resolution(client, customer, tenant):
    ticket = client.post(
        "/api/v1/tickets",
        json={"title": "Billing question", "customer_id": customer["id"]},
        headers={"Idempotency-Key": str(uuid4())},
    ).json()
    result = client.patch(
        f"/api/v1/tickets/{ticket['id']}",
        json={"status": "resolved", "assigned_user_id": tenant["user"]},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert result.status_code == 200, result.text
    assert result.json()["resolved_at"]
    client.post(f"/api/v1/tickets/{ticket['id']}/comments", json={"body": "Resolved by support"})
    detail = client.get(f"/api/v1/tickets/{ticket['id']}").json()
    assert detail["comments"][0]["body"] == "Resolved by support"
    assert client.get(f"/api/v1/customers/{customer['id']}").json()["tickets"][0]["id"] == ticket["id"]


def proposed(client, customer):
    result = client.patch(
        f"/api/v1/customers/{customer['id']}",
        json={"email": "new@example.com"},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert result.status_code == 200, result.text
    request = client.get("/api/v1/approvals").json()["items"][0]
    return result.json()["run_id"], request


def test_approval_survives_new_graph_and_executes_once(client, customer):
    run_id, request = proposed(client, customer)
    assert client.get(f"/api/v1/customers/{customer['id']}").json()["customer"]["email"] == "ada@example.com"
    assert client.post(f"/api/v1/approvals/{request['id']}/approve").status_code == 200
    # drive creates a fresh PostgresSaver and graph: no in-memory workflow state is reused.
    list(drive(run_id, resume=True))
    list(drive(run_id, resume=True))
    assert client.get(f"/api/v1/customers/{customer['id']}").json()["customer"]["email"] == "new@example.com"
    detail = client.get(f"/api/v1/agents/runs/{run_id}").json()
    assert detail["run"]["status"] == "succeeded"
    assert len(detail["tools"]) == 1
    assert detail["approvals"][0]["status"] == "executed"
    assert client.post(f"/api/v1/approvals/{request['id']}/reject").status_code == 409


@pytest.mark.parametrize("decision", ["reject", "cancel"])
def test_reject_cancel_never_mutate(client, customer, decision):
    run_id, request = proposed(client, customer)
    client.post(f"/api/v1/approvals/{request['id']}/{decision}")
    list(drive(run_id, resume=True))
    assert client.get(f"/api/v1/customers/{customer['id']}").json()["customer"]["email"] == "ada@example.com"
    assert client.get(f"/api/v1/agents/runs/{run_id}").json()["run"]["status"] == "rejected"


def test_approval_resource_changes_fail_closed(client, customer):
    run_id, request = proposed(client, customer)
    client.patch(
        f"/api/v1/customers/{customer['id']}",
        json={"company": "Changed"},
        headers={"Idempotency-Key": str(uuid4())},
    )
    client.post(f"/api/v1/approvals/{request['id']}/approve")
    list(drive(run_id, resume=True))
    assert client.get(f"/api/v1/agents/runs/{run_id}").json()["run"]["error_code"] == "resource_changed"
    assert client.get(f"/api/v1/customers/{customer['id']}").json()["customer"]["email"] == "ada@example.com"


def test_approval_expired_or_permission_revoked(client, customer, tenant):
    run_id, request = proposed(client, customer)
    with SessionLocal() as db:
        row = db.get(m.Approval, request["id"])
        row.expires_at = m.now() - timedelta(seconds=1)
        db.commit()
    client.post(f"/api/v1/approvals/{request['id']}/approve")
    list(drive(run_id, resume=True))
    assert client.get(f"/api/v1/customers/{customer['id']}").json()["customer"]["email"] == "ada@example.com"


def test_requester_role_rechecked_after_approval(client, customer, tenant):
    run_id, request = proposed(client, customer)
    client.post(f"/api/v1/approvals/{request['id']}/approve")
    with SessionLocal() as db:
        row = db.scalar(select(m.Membership).where(m.Membership.user_id == tenant["user"]))
        row.role = "viewer"
        db.commit()
    list(drive(run_id, resume=True))
    assert client.get(f"/api/v1/agents/runs/{run_id}").json()["run"]["error_code"] == "forbidden"


def test_tampered_approval_payload_rejected(client, customer):
    run_id, request = proposed(client, customer)
    client.post(f"/api/v1/approvals/{request['id']}/approve")
    with SessionLocal() as db:
        row = db.get(m.Approval, request["id"])
        row.payload = {"id": customer["id"], "changes": {"email": "evil@example.com"}}
        db.commit()
    list(drive(run_id, resume=True))
    assert client.get(f"/api/v1/agents/runs/{run_id}").json()["run"]["error_code"] == "approval_required"


def next_slot(client, tenant):
    date = (datetime.now(UTC) + timedelta(days=2)).date().isoformat()
    return client.post(
        "/api/v1/appointments/availability", json={"date": date, "appointment_type_id": tenant["type"]}
    ).json()["slots"][0]["starts_at"]


def test_concurrent_booking_database_constraint(client, customer, tenant):
    start = next_slot(client, tenant)
    actor = Actor(tenant["user"], tenant["org"], "owner")
    body = {
        "customer_id": customer["id"],
        "appointment_type_id": tenant["type"],
        "title": "Consultation",
        "starts_at": start,
    }

    def attempt(_):
        with SessionLocal() as db:
            try:
                return execute(db, actor, "create_appointment", body, str(uuid4()))["data"]["id"]
            except DomainError as exc:
                return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, range(2)))
    assert results.count("conflict") == 1
    assert client.get("/api/v1/appointments").json()["total"] == 1
    # Adjacent slots are legal: the constraint uses a half-open interval.
    body["starts_at"] = (datetime.fromisoformat(start) + timedelta(minutes=30)).isoformat()
    assert (
        client.post("/api/v1/appointments", json=body, headers={"Idempotency-Key": str(uuid4())}).status_code
        == 200
    )


def test_schedule_validation_and_cancel(client, customer, tenant):
    body = {
        "customer_id": customer["id"],
        "appointment_type_id": tenant["type"],
        "title": "Consultation",
        "starts_at": "2030-01-01T03:00:00",
    }
    assert (
        client.post("/api/v1/appointments", json=body, headers={"Idempotency-Key": str(uuid4())}).status_code
        == 422
    )
    body["starts_at"] += "+00:00"
    assert (
        client.post("/api/v1/appointments", json=body, headers={"Idempotency-Key": str(uuid4())}).status_code
        == 400
    )
    body["starts_at"] = next_slot(client, tenant)
    row = client.post("/api/v1/appointments", json=body, headers={"Idempotency-Key": str(uuid4())}).json()
    client.post(f"/api/v1/appointments/{row['id']}/cancel", headers={"Idempotency-Key": str(uuid4())})
    approval = client.get("/api/v1/approvals").json()["items"][0]
    client.post(f"/api/v1/approvals/{approval['id']}/approve")
    list(drive(approval["run_id"], resume=True))
    assert client.get("/api/v1/appointments").json()["items"][0]["status"] == "cancelled"


def test_appointment_type_management_and_timezone_aware_tasks(client, tenant):
    response = client.post(
        "/api/v1/appointment-types", json={"name": "Extended consultation", "duration_minutes": 45}
    )
    assert response.status_code == 200, response.text
    appointment_type = response.json()
    assert appointment_type["duration_minutes"] == 45
    slots = client.post(
        "/api/v1/appointments/availability",
        json={
            "date": (datetime.now(UTC) + timedelta(days=3)).date().isoformat(),
            "appointment_type_id": appointment_type["id"],
        },
    ).json()["slots"]
    assert all(
        datetime.fromisoformat(item["ends_at"]) - datetime.fromisoformat(item["starts_at"])
        == timedelta(minutes=45)
        for item in slots
    )
    assert (
        client.patch(
            f"/api/v1/appointment-types/{appointment_type['id']}", json={"duration_minutes": 15}
        ).json()["duration_minutes"]
        == 15
    )
    assert (
        client.post(
            "/api/v1/tasks",
            json={"title": "Naive due date", "due_at": "2030-01-01T09:00:00"},
            headers={"Idempotency-Key": str(uuid4())},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/tasks",
            json={"title": "Zoned due date", "due_at": "2030-01-01T09:00:00-05:00"},
            headers={"Idempotency-Key": str(uuid4())},
        ).status_code
        == 200
    )


def test_ingestion_retrieval_delete_and_isolation(client, tenant):
    response = client.post(
        "/api/v1/documents",
        files={"file": ("policy.md", b"Refunds are available within 30 days of purchase.", "text/markdown")},
    )
    assert response.status_code == 200, response.text
    doc = response.json()
    ingest(doc["id"])
    hits = client.post("/api/v1/knowledge/search", json={"query": "refunds purchase"}).json()["hits"]
    assert hits and hits[0]["document_id"] == doc["id"]
    assert "30 days" in hits[0]["content"]
    with SessionLocal() as db:
        other = m.Organization(name="Other")
        db.add(other)
        db.commit()
        from app.services.knowledge import search

        assert not search(db, Actor(tenant["user"], other.id, "viewer"), s.Search(query="refunds purchase"))[
            "hits"
        ]
        db.delete(other)
        db.commit()
    assert client.delete(f"/api/v1/documents/{doc['id']}").status_code == 200
    assert not client.post("/api/v1/knowledge/search", json={"query": "refunds purchase"}).json()["hits"]


@pytest.mark.parametrize("name,data", [("bad.exe", b"hello"), ("empty.txt", b"")])
def test_upload_validation(client, name, data):
    assert client.post("/api/v1/documents", files={"file": (name, data)}).status_code in {413, 415}


def test_agent_writes_real_ticket_sse_history(client):
    conversation = client.post("/api/v1/conversations").json()
    request_id = str(uuid4())
    body = {
        "conversation_id": conversation["id"],
        "message": "Create ticket: Billing question",
        "request_id": request_id,
    }
    first = client.post("/api/v1/agents/chat", json=body)
    assert "event: step" in first.text and "event: answer" in first.text, first.text
    assert client.get("/api/v1/tickets").json()["total"] == 1
    assert client.post("/api/v1/agents/chat", json=body).status_code == 200
    assert client.get("/api/v1/tickets").json()["total"] == 1
    messages = client.get(f"/api/v1/conversations/{conversation['id']}").json()["messages"]
    assert len(messages) == 2
    assert client.get("/api/v1/dashboard/summary").json()["runs"] == 1


def test_no_evidence_no_fabrication(client):
    conversation = client.post("/api/v1/conversations").json()
    response = client.post(
        "/api/v1/agents/chat",
        json={
            "conversation_id": conversation["id"],
            "message": "What is the refund policy?",
            "request_id": str(uuid4()),
        },
    )
    assert "sufficient evidence" in response.text
    assert client.get("/api/v1/tickets").json()["total"] == 0
