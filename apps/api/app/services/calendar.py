"""Future integration boundary. The shipped system uses only its internal PostgreSQL calendar."""

from datetime import datetime
from typing import Protocol


class CalendarProvider(Protocol):
    def busy_intervals(
        self, organization_id: str, starts_at: datetime, ends_at: datetime
    ) -> list[tuple[datetime, datetime]]: ...
    def publish(self, organization_id: str, appointment_id: str, idempotency_key: str) -> str: ...
    def remove(self, organization_id: str, external_id: str, idempotency_key: str) -> None: ...
