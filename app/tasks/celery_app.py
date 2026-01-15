from __future__ import annotations

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "salon_whatsapp_bot",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
)

# periodic schedule
celery_app.conf.beat_schedule = {
    "enqueue-due-tasks-every-60s": {
        "task": "app.tasks.jobs.enqueue_due_tasks",
        "schedule": 60.0,
    },
}
