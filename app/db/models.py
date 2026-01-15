from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TaskStatus(str, enum.Enum):
    scheduled = "scheduled"
    queued = "queued"
    done = "done"
    failed = "failed"
    canceled = "canceled"


class OutboxStatus(str, enum.Enum):
    queued = "queued"
    sent = "sent"
    failed = "failed"


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phone_e164: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    locale: Mapped[str] = mapped_column(String(16), default="ru")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    altegio_company_id: Mapped[int] = mapped_column(Integer, index=True)
    altegio_appointment_id: Mapped[int] = mapped_column(Integer, index=True)

    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    client: Mapped["Client"] = relationship()

    status: Mapped[str] = mapped_column(String(64), default="unknown", index=True)

    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    staff_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    service_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("altegio_company_id", "altegio_appointment_id", name="uq_appt_altegio"),
    )


class MessageTemplate(Base):
    __tablename__ = "message_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(64), index=True)
    language: Mapped[str] = mapped_column(String(16), default="ru", index=True)

    text: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (UniqueConstraint("key", "language", name="uq_template_key_lang"),)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    appointment_id: Mapped[int] = mapped_column(ForeignKey("appointments.id"), index=True)
    appointment: Mapped["Appointment"] = relationship()

    type: Mapped[str] = mapped_column(String(64), index=True)
    planned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.scheduled, index=True)

    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OutboxMessage(Base):
    __tablename__ = "outbox_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    task: Mapped["Task"] = relationship()

    to_phone: Mapped[str] = mapped_column(String(32), index=True)
    template_key: Mapped[str] = mapped_column(String(64), index=True)
    template_version: Mapped[int] = mapped_column(Integer, default=1)

    rendered_text: Mapped[str] = mapped_column(Text)

    status: Mapped[OutboxStatus] = mapped_column(Enum(OutboxStatus), default=OutboxStatus.queued, index=True)
    provider_message_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class EventLog(Base):
    __tablename__ = "event_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    event_name: Mapped[str] = mapped_column(String(128), index=True)

    appointment_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    client_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    task_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    outbox_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    template_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    template_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)


class WebhookDedup(Base):
    __tablename__ = "webhook_dedup"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)  # 'altegio'
    event_key: Mapped[str] = mapped_column(String(128), index=True)  # request-id or sha256
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("provider", "event_key", name="uq_webhook_dedup"),)


Index("ix_tasks_due", Task.status, Task.planned_at)
Index("ix_outbox_queue", OutboxMessage.status, OutboxMessage.created_at)
