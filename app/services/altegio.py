from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from app.core.config import settings


@dataclass
class AppointmentInfo:
    appointment_id: int
    client_phone_e164: str
    client_name: str | None
    starts_at: datetime
    ends_at: datetime
    staff_name: str | None
    service_name: str | None
    source: str | None
    status: str


class AltegioClient:
    def __init__(self) -> None:
        self.base = settings.ALTEGIO_API_BASE.rstrip("/")
        self.token = settings.ALTEGIO_API_TOKEN
        self.company_id = settings.ALTEGIO_COMPANY_ID

    def _headers(self) -> dict:
        # В Altegio часто используется Bearer/Token заголовок — подстрой под их доки.
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }

    def get_appointment(self, appointment_id: int) -> AppointmentInfo:
        """
        TODO: заменить URL/парсинг под реальные поля Altegio.
        Сейчас сделано как каркас.
        """
        url = f"{self.base}/api/v1/appointments/{appointment_id}"
        with httpx.Client(timeout=15) as client:
            r = client.get(url, headers=self._headers(), params={"company_id": self.company_id})
            r.raise_for_status()
            data = r.json()

        # !!! Ниже — пример. Подставишь реальные ключи из Altegio ответа.
        starts = datetime.fromisoformat(data["starts_at"]).astimezone(timezone.utc)
        ends = datetime.fromisoformat(data["ends_at"]).astimezone(timezone.utc)

        return AppointmentInfo(
            appointment_id=appointment_id,
            client_phone_e164=data["client"]["phone"],
            client_name=data["client"].get("name"),
            starts_at=starts,
            ends_at=ends,
            staff_name=data.get("staff", {}).get("name"),
            service_name=data.get("service", {}).get("name"),
            source=data.get("source"),
            status=data.get("status", "unknown"),
        )
