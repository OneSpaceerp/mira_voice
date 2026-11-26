"""Call records, call events (the raw stream from ARI) and recordings."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from mira_core.models.base import Base, TenantScoped, UUIDPrimaryKey, str_enum


class CallDirection(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    INTERNAL = "internal"


class CallDisposition(StrEnum):
    ANSWERED = "answered"
    NO_ANSWER = "no_answer"
    BUSY = "busy"
    FAILED = "failed"
    ABANDONED = "abandoned"  # caller hung up while waiting in a queue / IVR


class Call(UUIDPrimaryKey, TenantScoped, Base):
    """One customer-facing call (an Asterisk linkedid). Updated as events arrive (task 1.3)."""

    __tablename__ = "calls"

    asterisk_linkedid: Mapped[str] = mapped_column(String(64), unique=True)
    direction: Mapped[CallDirection] = mapped_column(str_enum(CallDirection, "call_direction"))
    caller_number: Mapped[str] = mapped_column(String(64))
    called_number: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    answered_at: Mapped[datetime | None]
    ended_at: Mapped[datetime | None]
    disposition: Mapped[CallDisposition | None] = mapped_column(
        str_enum(CallDisposition, "call_disposition")
    )
    hangup_cause: Mapped[int | None]
    queue_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("queues.id", ondelete="SET NULL"))
    agent_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    trunk_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("trunks.id", ondelete="SET NULL"))

    __table_args__ = (
        Index("ix_calls_tenant_started", "tenant_id", "started_at"),
        # calls still in progress: the event worker reconciles them after every restart
        Index("ix_calls_open", "tenant_id", postgresql_where=text("ended_at IS NULL")),
        CheckConstraint(
            "answered_at IS NULL OR answered_at >= started_at", name="answer_after_start"
        ),
        CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="end_after_start"),
    )


class CallEvent(TenantScoped, Base):
    """Append-only event stream (StasisStart, QueueCallerJoin, AgentConnect, …) feeding
    per-call and 15-minute rollups (task 2.4). Big table: bigint id, no updated_at."""

    __tablename__ = "call_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    call_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"))
    occurred_at: Mapped[datetime] = mapped_column(server_default=func.now())
    type: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict[str, Any]] = mapped_column(default=dict)

    __table_args__ = (
        Index("ix_call_events_call_time", "call_id", "occurred_at"),
        Index("ix_call_events_tenant_time", "tenant_id", "occurred_at"),
    )


class Recording(UUIDPrimaryKey, TenantScoped, Base):
    """A call recording stored in MinIO (task 1.6). Deleted after retain_until."""

    __tablename__ = "recordings"

    call_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("calls.id", ondelete="RESTRICT"), index=True
    )
    object_key: Mapped[str] = mapped_column(String(512), unique=True)
    format: Mapped[str] = mapped_column(String(16), default="wav")
    duration_seconds: Mapped[int]
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    retain_until: Mapped[datetime] = mapped_column(index=True)

    __table_args__ = (
        CheckConstraint("duration_seconds >= 0", name="duration_positive"),
        CheckConstraint("size_bytes >= 0", name="size_positive"),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="sha256_hex"),
    )
