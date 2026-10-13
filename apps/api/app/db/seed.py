from sqlalchemy import select

from app.auth.security import passwords
from app.core.config import settings
from app.db.session import SessionLocal
from app.models import entities as m


def seed():
    config = settings()
    if not config.demo_password or len(config.demo_password) < 12:
        raise ValueError("Set a DEMO_PASSWORD with at least 12 characters")
    if config.environment == "production":
        raise ValueError("Demo seeding is disabled in production")
    with SessionLocal() as db:
        if db.scalar(select(m.User).where(m.User.email == config.demo_email.lower())):
            print("Demo owner already exists; no records changed.")
            return
        org = m.Organization(
            name="Acme Operations", business_information="Demo organization. Monday–Friday, 9am–5pm."
        )
        user = m.User(
            email=config.demo_email.lower(),
            name="Demo Owner",
            password_hash=passwords.hash(config.demo_password),
        )
        db.add_all([org, user])
        db.flush()
        db.add(m.Membership(organization_id=org.id, user_id=user.id, role="owner"))
        db.add(m.AppointmentType(organization_id=org.id, name="Consultation", duration_minutes=30))
        for day in range(5):
            db.add(m.BusinessHours(organization_id=org.id, weekday=day, open_minute=540, close_minute=1020))
        # Empty business data by design: dashboard metrics always reflect real user-created records.
        db.commit()
        print("Demo organization and owner created. Sign in using your configured credentials.")


if __name__ == "__main__":
    seed()
