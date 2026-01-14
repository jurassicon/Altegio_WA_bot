from __future__ import annotations

import logging
from datetime import datetime, timezone

import redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import OutboxMessage, OutboxStatus, TaskStatus
from app.db.session import SessionLocal
from app.services.analytics import log_event
from app.services.rate_limit import set_next_allowed, wait_for_slot
from app.services.whatsapp import WhatsAppClient

logger = logging.getLogger(__name__)


def _now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def fetch_next_queued(db: Session) -> OutboxMessage | None:
    return db.execute(
        select(OutboxMessage)
        .where(OutboxMessage.status == OutboxStatus.queued)
        .order_by(OutboxMessage.created_at.asc())
        .limit(1)
    ).scalar_one_or_none()


def main() -> None:
    r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    wa = WhatsAppClient()

    logger.info("Sender started")

    while True:
        # 1) wait global rate-limit slot
        wait_for_slot(r, settings.WHATSAPP_RATE_LIMIT_SECONDS)

        # 2) pick one message
        with SessionLocal() as db:
            msg = fetch_next_queued(db)
            if not msg:
                # no messages: back off a bit
                set_next_allowed(r, _now_ts() + 5)
                db.commit()
                continue

            task = msg.task
            appt = task.appointment
            client = appt.client

            try:
                provider_id = wa.send_text(msg.to_phone, msg.rendered_text)
                msg.status = OutboxStatus.sent
                msg.provider_message_id = provider_id
                msg.sent_at = datetime.now(timezone.utc)

                task.status = TaskStatus.done

                log_event(
                    db,
                    "message.sent",
                    appointment_id=appt.id,
                    client_id=client.id,
                    task_id=task.id,
                    outbox_id=msg.id,
                    template_key=msg.template_key,
                    template_version=msg.template_version,
                    meta={"provider_message_id": provider_id},
                )

                db.commit()

                # 3) set next allowed time (strict 1 per N sec)
                set_next_allowed(r, _now_ts() + settings.WHATSAPP_RATE_LIMIT_SECONDS)

            except Exception as e:
                msg.status = OutboxStatus.failed
                msg.error = str(e)
                task.status = TaskStatus.failed
                task.last_error = str(e)

                log_event(
                    db,
                    "message.failed",
                    appointment_id=appt.id,
                    client_id=client.id,
                    task_id=task.id,
                    outbox_id=msg.id,
                    template_key=msg.template_key,
                    template_version=msg.template_version,
                    meta={"error": str(e)},
                )

                db.commit()

                # даже при ошибке соблюдаем лимит
                set_next_allowed(r, _now_ts() + settings.WHATSAPP_RATE_LIMIT_SECONDS)


if __name__ == "__main__":
    logging.basicConfig(level=settings.LOG_LEVEL)
    main()
