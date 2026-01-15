from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import EventLog


def log_event(
    db: Session,
    event_name: str,
    appointment_id: int | None = None,
    client_id: int | None = None,
    task_id: int | None = None,
    outbox_id: int | None = None,
    template_key: str | None = None,
    template_version: int | None = None,
    meta: dict | None = None,
) -> None:
    e = EventLog(
        event_name=event_name,
        appointment_id=appointment_id,
        client_id=client_id,
        task_id=task_id,
        outbox_id=outbox_id,
        template_key=template_key,
        template_version=template_version,
        meta_json=meta or {},
    )
    db.add(e)
