from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import WebhookDedup
from app.db.session import AsyncSessionLocal
from app.tasks.jobs import process_altegio_event  # Celery task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhooks"])


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


@router.post("/altegio")
async def altegio_webhook(
    request: Request,
    x_altegio_secret: str | None = Header(default=None),
    x_request_id: str | None = Header(default=None),
):
    # 1) simple shared-secret check
    if x_altegio_secret != settings.ALTEGIO_WEBHOOK_SECRET:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad webhook secret")

    body_bytes = await request.body()
    if not body_bytes:
        raise HTTPException(status_code=400, detail="Empty body")

    # 2) idempotency key: prefer request id, else sha256(body)
    if x_request_id:
        event_key = f"rid:{x_request_id}"
    else:
        digest = hashlib.sha256(body_bytes).hexdigest()
        event_key = f"sha256:{digest}"

    # 3) dedup in DB
    async with AsyncSessionLocal() as db:
        exists = await db.execute(
            select(WebhookDedup).where(WebhookDedup.provider == "altegio", WebhookDedup.event_key == event_key)
        )
        if exists.scalar_one_or_none():
            return {"status": "duplicate_ignored", "event_key": event_key}

        db.add(WebhookDedup(provider="altegio", event_key=event_key))
        await db.commit()

    # 4) enqueue processing into Celery (async -> background)
    try:
        payload = json.loads(body_bytes.decode("utf-8"))
    except Exception:
        payload = {"raw": body_bytes.decode("utf-8", errors="replace")}

    process_altegio_event.delay(
        {
            "event_key": event_key,
            "received_at": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
    )

    logger.info("Altegio webhook accepted", extra={"event_key": event_key})
    return {"status": "accepted", "event_key": event_key}
