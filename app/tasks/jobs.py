from __future__ import annotations

from datetime import datetime, timedelta, timezone

import logging
from celery.utils.log import get_task_logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Appointment, Client, OutboxMessage, Task, TaskStatus
from app.db.session import SessionLocal
from app.services.analytics import log_event
from app.services.templating import render_template
from app.tasks import celery_app


logger = get_task_logger(__name__)
py_logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value) -> datetime | None:
    try:
        if not value:
            return None
        dt = datetime.fromisoformat(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def upsert_client(db: Session, phone: str, name: str | None) -> Client:
    c = db.execute(select(Client).where(Client.phone_e164 == phone)).scalar_one_or_none()
    if c:
        if name and c.name != name:
            c.name = name
        return c
    c = Client(phone_e164=phone, name=name, locale="ru")
    db.add(c)
    db.flush()
    return c


def upsert_appointment(
    db: Session,
    company_id: int,
    appt_id: int,
    client: Client,
    starts_at: datetime,
    ends_at: datetime,
    status: str,
    staff_name: str | None,
    service_name: str | None,
    source: str | None,
) -> Appointment:
    a = db.execute(
        select(Appointment).where(
            Appointment.alteg.io_company_id == company_id,  # type: ignore[attr-defined]
            Appointment.alteg.io_appointment_id == appt_id,  # type: ignore[attr-defined]
        )
    ).scalar_one_or_none()

    if a:
        a.client_id = client.id
        a.starts_at = starts_at
        a.ends_at = ends_at
        a.status = status
        a.staff_name = staff_name
        a.service_name = service_name
        a.source = source
        return a

    a = Appointment(
        altegio_company_id=company_id,
        altegio_appointment_id=appt_id,
        client_id=client.id,
        starts_at=starts_at,
        ends_at=ends_at,
        status=status,
        staff_name=staff_name,
        service_name=service_name,
        source=source,
    )
    db.add(a)
    db.flush()
    return a


def schedule_default_tasks(db: Session, appt: Appointment, client: Client) -> None:
    """
    MVP-логика:
    - created: подтверждение сразу
    - reminders: за 24ч и за 2ч
    - review: через 2ч после визита
    - rebook: через 21 день после визита
    """
    # created now
    db.add(
        Task(
            appointment_id=appt.id,
            type="send_created",
            planned_at=_now(),
            status=TaskStatus.scheduled,
            payload_json={"template_key": "APPT_CREATED"},
        )
    )

    # reminders
    db.add(
        Task(
            appointment_id=appt.id,
            type="reminder_24h",
            planned_at=appt.starts_at - timedelta(hours=24),
            status=TaskStatus.scheduled,
            payload_json={"template_key": "REMINDER_24H"},
        )
    )
    db.add(
        Task(
            appointment_id=appt.id,
            type="reminder_2h",
            planned_at=appt.starts_at - timedelta(hours=2),
            status=TaskStatus.scheduled,
            payload_json={"template_key": "REMINDER_2H"},
        )
    )

    # review request
    db.add(
        Task(
            appointment_id=appt.id,
            type="review_request",
            planned_at=appt.ends_at + timedelta(hours=2),
            status=TaskStatus.scheduled,
            payload_json={"template_key": "REVIEW_REQUEST"},
        )
    )

    # rebook invite
    db.add(
        Task(
            appointment_id=appt.id,
            type="rebook_invite",
            planned_at=appt.ends_at + timedelta(days=21),
            status=TaskStatus.scheduled,
            payload_json={"template_key": "REBOOK_INVITE"},
        )
    )


def build_context(appt: Appointment, client: Client) -> dict:
    return {
        "client_name": client.name or "😊",
        "date": appt.starts_at.astimezone(timezone.utc).strftime("%d.%m.%Y"),
        "time": appt.starts_at.astimezone(timezone.utc).strftime("%H:%M"),
        "staff": appt.staff_name or "",
        "service": appt.service_name or "",
    }


@celery_app.task(name="app.tasks.jobs.process_altegio_event")
def process_altegio_event(event: dict) -> dict:
    """
    event = {"event_key": "...", "received_at": "...", "payload": {...}}
    Подстроишь payload-парсинг под реальные поля Altegio webhook.
    """
    payload = event.get("payload") or {}
    event_key = event.get("event_key", "")

    event_type = str(payload.get("type", "unknown"))
    appt_id = int(payload.get("appointment_id", 0)) if payload.get("appointment_id") else 0
    if not appt_id:
        logger.warning("No appointment_id in payload", extra={"event_key": event_key})
        return {"status": "ignored_no_appointment_id", "event_key": event_key}

    phone = str(payload.get("client_phone", "")).strip()
    if not phone:
        return {"status": "ignored_no_phone", "event_key": event_key}

    name = payload.get("client_name")
    starts_at = _parse_dt(payload.get("starts_at")) or _now()
    ends_at = _parse_dt(payload.get("ends_at")) or (starts_at + timedelta(hours=1))
    staff_name = payload.get("staff_name")
    service_name = payload.get("service_name")
    source = payload.get("source")
    status_str = str(payload.get("status", event_type))

    with SessionLocal() as db:
        client = upsert_client(db, phone, name)
        appt = upsert_appointment(
            db=db,
            company_id=settings.ALTEGIO_COMPANY_ID,
            appt_id=appt_id,
            client=client,
            starts_at=starts_at,
            ends_at=ends_at,
            status=status_str,
            staff_name=staff_name,
            service_name=service_name,
            source=source,
        )

        log_event(
            db,
            event_name=f"altegio.webhook.{event_type}",
            appointment_id=appt.id,
            client_id=client.id,
            meta={"event_key": event_key},
        )

        # MVP: на created — планируем всё
        if event_type == "created":
            schedule_default_tasks(db, appt, client)
            log_event(db, "task.scheduled.default_set", appointment_id=appt.id, client_id=client.id)

        # На canceled/updated можно добавить отдельные task-ы позже
        db.commit()

    return {"status": "ok", "event_key": event_key}


@celery_app.task(name="app.tasks.jobs.enqueue_due_tasks")
def enqueue_due_tasks() -> dict:
    """
    Каждую минуту:
    - берём tasks со статусом scheduled и planned_at <= now
    - рендерим текст через шаблон
    - кладём в outbox
    """
    now = _now()
    made = 0

    with SessionLocal() as db:
        due = db.execute(
            select(Task)
            .where(Task.status == TaskStatus.scheduled, Task.planned_at <= now)
            .order_by(Task.planned_at.asc())
            .limit(200)
        ).scalars().all()

        for task in due:
            appt = task.appointment
            client = appt.client
            template_key = task.payload_json.get("template_key")
            if not template_key:
                task.status = TaskStatus.failed
                task.last_error = "No template_key in payload_json"
                log_event(db, "task.failed", appointment_id=appt.id, client_id=client.id, task_id=task.id)
                continue

            try:
                context = build_context(appt, client)
                rendered, version = render_template(db, template_key, client.locale, context)

                outbox = OutboxMessage(
                    task_id=task.id,
                    to_phone=client.phone_e164,
                    template_key=template_key,
                    template_version=version,
                    rendered_text=rendered,
                )
                db.add(outbox)
                db.flush()

                task.status = TaskStatus.queued
                log_event(
                    db,
                    "message.queued",
                    appointment_id=appt.id,
                    client_id=client.id,
                    task_id=task.id,
                    outbox_id=outbox.id,
                    template_key=template_key,
                    template_version=version,
                )
                made += 1
            except Exception as e:
                task.status = TaskStatus.failed
                task.last_error = str(e)
                log_event(
                    db,
                    "task.failed",
                    appointment_id=appt.id,
                    client_id=client.id,
                    task_id=task.id,
                    meta={"error": str(e), "template_key": template_key},
                )

        db.commit()

    return {"enqueued": made}
