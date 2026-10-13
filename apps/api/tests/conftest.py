from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.security import passwords
from app.core.config import settings
from app.db.initialize import initialize
from app.db.session import SessionLocal
from app.main import app
from app.models import entities as m


@pytest.fixture(scope="session", autouse=True)
def database():
    assert settings().database_url.rsplit("/", 1)[-1] == "operations_test", (
        "Tests require an isolated operations_test database"
    )
    assert settings().ai_provider == "demo", "Tests use the deterministic provider"
    initialize()


@pytest.fixture
def tenant():
    token = uuid4().hex[:10]
    with SessionLocal() as db:
        org = m.Organization(name="Test " + token)
        user = m.User(
            name="Test Owner",
            email=f"{token}@example.com",
            password_hash=passwords.hash("test-password-strong"),
        )
        db.add_all([org, user])
        db.flush()
        db.add(m.Membership(organization_id=org.id, user_id=user.id, role="owner"))
        kind = m.AppointmentType(organization_id=org.id, name="Consultation", duration_minutes=30)
        db.add(kind)
        for day in range(7):
            db.add(m.BusinessHours(organization_id=org.id, weekday=day, open_minute=540, close_minute=1020))
        db.commit()
        result = {"org": org.id, "user": user.id, "email": user.email, "type": kind.id}
    yield result
    # Cleanup only this fixture's tenant. Checkpoint tables are intentionally retained for recovery tests.
    with SessionLocal() as db:
        db.delete(db.get(m.Organization, result["org"]))
        db.commit()
        db.delete(db.get(m.User, result["user"]))
        db.commit()


@pytest.fixture
def client(tenant):
    with TestClient(app, client=("test-" + uuid4().hex, 50000)) as client:
        result = client.post(
            "/api/v1/auth/login", json={"email": tenant["email"], "password": "test-password-strong"}
        )
        assert result.status_code == 200, result.text
        client.headers["X-CSRF-Token"] = result.json()["csrf_token"]
        yield client


@pytest.fixture
def key():
    return {"Idempotency-Key": str(uuid4())}


@pytest.fixture
def customer(client, key):
    response = client.post(
        "/api/v1/customers", json={"first_name": "Ada", "email": "ada@example.com"}, headers=key
    )
    assert response.status_code == 200, response.text
    return response.json()
