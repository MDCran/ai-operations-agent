import argparse
import getpass
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.auth.security import passwords
from app.db.session import SessionLocal
from app.models import entities as m


def main():
    parser = argparse.ArgumentParser(description="Provision an organization and its initial owner.")
    parser.add_argument("--organization", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--timezone", default="America/New_York")
    args = parser.parse_args()
    from pydantic import EmailStr, TypeAdapter

    email = str(TypeAdapter(EmailStr).validate_python(args.email)).lower()
    ZoneInfo(args.timezone)
    password = getpass.getpass("Owner password (12+ characters): ")
    if len(password) < 12 or password != getpass.getpass("Confirm password: "):
        raise ValueError("Password too short or confirmation did not match")
    with SessionLocal() as db:
        if db.scalar(select(m.User).where(m.User.email == email)):
            raise ValueError("Account already exists; no records changed")
        org = m.Organization(name=args.organization, timezone=args.timezone)
        user = m.User(name=args.name, email=email, password_hash=passwords.hash(password))
        db.add_all([org, user])
        db.flush()
        db.add(m.Membership(organization_id=org.id, user_id=user.id, role="owner"))
        db.add(m.AppointmentType(organization_id=org.id, name="Consultation", duration_minutes=30))
        for day in range(5):
            db.add(m.BusinessHours(organization_id=org.id, weekday=day, open_minute=540, close_minute=1020))
        db.commit()
        print("Organization and owner created.")


if __name__ == "__main__":
    main()
