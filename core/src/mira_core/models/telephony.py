"""Telephony configuration: extensions, trunks, queues, IVR flows.
Mira Core turns these rows into Asterisk / Kamailio config (task 1.1)."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from mira_core.models.base import Base, TenantScoped, Timestamps, UUIDPrimaryKey, str_enum
from mira_core.models.tenancy import Locale


class Extension(UUIDPrimaryKey, Timestamps, TenantScoped, Base):
    """A SIP device account (desk phone, Mira Desk WebRTC softphone, Mira Phone)."""

    __tablename__ = "extensions"

    number: Mapped[str] = mapped_column(String(16))  # dialled inside the tenant, e.g. "1001"
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    display_name: Mapped[str] = mapped_column(String(100))
    # Globally unique SIP auth user (all tenants share the SIP edge)
    sip_username: Mapped[str] = mapped_column(String(64), unique=True)
    # Digest HA1 = md5(username:realm:password) — Asterisk auth_type=md5; no clear password stored
    sip_ha1: Mapped[str] = mapped_column(String(32))
    sip_realm: Mapped[str] = mapped_column(String(64), default="mira")
    webrtc: Mapped[bool] = mapped_column(default=True)
    enabled: Mapped[bool] = mapped_column(default=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "number"),
        CheckConstraint("number ~ '^[0-9]{2,16}$'", name="number_digits"),
        CheckConstraint("sip_ha1 ~ '^[0-9a-f]{32}$'", name="ha1_hex"),
    )


class TrunkKind(StrEnum):
    SIP_REGISTER = "sip_register"  # we register to the carrier (e.g. WE)
    SIP_IP_AUTH = "sip_ip_auth"  # carrier authenticates our IP
    GSM_GATEWAY = "gsm_gateway"  # Yeastar / Dinstar box on the LAN


class SipTransport(StrEnum):
    UDP = "udp"
    TCP = "tcp"
    TLS = "tls"


class Trunk(UUIDPrimaryKey, Timestamps, TenantScoped, Base):
    """A carrier connection (task 1.2, ADR 0007).

    sip_register: Mira registers to the carrier (host = registrar) with auth_username/secret.
    sip_ip_auth:  the carrier trusts our IP; calls from `inbound_ips` are this trunk.
    gsm_gateway:  a Yeastar/Dinstar box registers to Mira like a phone (Mira is the registrar).
    """

    __tablename__ = "trunks"

    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[TrunkKind] = mapped_column(str_enum(TrunkKind, "trunk_kind"))
    host: Mapped[str] = mapped_column(String(253))
    port: Mapped[int] = mapped_column(default=5060)
    transport: Mapped[SipTransport] = mapped_column(
        str_enum(SipTransport, "trunk_transport"), default=SipTransport.UDP
    )
    auth_username: Mapped[str | None] = mapped_column(String(128))
    from_domain: Mapped[str | None] = mapped_column(String(253))
    caller_id_number: Mapped[str | None] = mapped_column(String(32))
    max_channels: Mapped[int] = mapped_column(default=30)
    enabled: Mapped[bool] = mapped_column(default=True)
    # Carrier password, Fernet-encrypted with MIRA_DATA_KEY (crypto.py). Never returned by the API.
    auth_secret_enc: Mapped[str | None] = mapped_column(Text)
    # gsm_gateway: Mira is the registrar; only the digest HA1 of the gateway's password is kept.
    sip_ha1: Mapped[str | None] = mapped_column(String(32))
    # Signalling IPs the carrier calls us from (Kamailio identifies the trunk by them).
    inbound_ips: Mapped[list[str]] = mapped_column(ARRAY(String(45)), default=list)

    @property
    def asterisk_id(self) -> str:
        """Endpoint / AOR id in Asterisk (also the registration contact user)."""
        return "trunk_" + self.id.hex

    __table_args__ = (
        UniqueConstraint("tenant_id", "name"),
        CheckConstraint("sip_ha1 IS NULL OR sip_ha1 ~ '^[0-9a-f]{32}$'", name="ha1_hex"),
        CheckConstraint("port BETWEEN 1 AND 65535", name="port_range"),
        CheckConstraint("max_channels > 0", name="max_channels_positive"),
    )


class QueueStrategy(StrEnum):
    """app_queue strategies."""

    RINGALL = "ringall"
    LEASTRECENT = "leastrecent"
    FEWESTCALLS = "fewestcalls"
    RANDOM = "random"
    RRMEMORY = "rrmemory"
    LINEAR = "linear"
    WRANDOM = "wrandom"


class Queue(UUIDPrimaryKey, Timestamps, TenantScoped, Base):
    __tablename__ = "queues"

    name: Mapped[str] = mapped_column(String(100))
    number: Mapped[str | None] = mapped_column(String(16))  # optional direct-dial number
    strategy: Mapped[QueueStrategy] = mapped_column(
        str_enum(QueueStrategy, "queue_strategy"), default=QueueStrategy.LEASTRECENT
    )
    ring_timeout_seconds: Mapped[int] = mapped_column(default=20)
    wrapup_seconds: Mapped[int] = mapped_column(default=10)
    max_wait_seconds: Mapped[int] = mapped_column(default=600)
    music_class: Mapped[str] = mapped_column(String(64), default="default")
    announce_position: Mapped[bool] = mapped_column(default=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name"),
        CheckConstraint("ring_timeout_seconds > 0", name="ring_timeout_positive"),
        CheckConstraint("wrapup_seconds >= 0", name="wrapup_positive"),
    )


class QueueMember(UUIDPrimaryKey, Timestamps, TenantScoped, Base):
    __tablename__ = "queue_members"

    queue_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("queues.id", ondelete="CASCADE"), index=True
    )
    extension_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("extensions.id", ondelete="CASCADE"), index=True
    )
    penalty: Mapped[int] = mapped_column(default=0)
    paused: Mapped[bool] = mapped_column(default=False)

    __table_args__ = (
        UniqueConstraint("queue_id", "extension_id"),
        CheckConstraint("penalty >= 0", name="penalty_positive"),
    )


class IvrFlow(UUIDPrimaryKey, Timestamps, TenantScoped, Base):
    """A Mira Flow (task 1.4, ADR 0009): a stable identity, the draft being edited, and which
    published version answers calls. Published versions are immutable (IvrFlowVersion), so
    a rollback only moves `published_version`."""

    __tablename__ = "ivr_flows"

    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(500), default="")
    draft: Mapped[dict[str, Any]] = mapped_column(default=dict)
    published_version: Mapped[int | None]
    # Optional internal number: dialling it inside the tenant runs the flow (tests, staff IVRs)
    number: Mapped[str | None] = mapped_column(String(16))

    __table_args__ = (
        UniqueConstraint("tenant_id", "name"),
        UniqueConstraint("tenant_id", "number"),
        CheckConstraint(
            "published_version IS NULL OR published_version > 0", name="published_positive"
        ),
        CheckConstraint("number IS NULL OR number ~ '^[0-9]{2,16}$'", name="number_digits"),
    )


class IvrFlowVersion(UUIDPrimaryKey, TenantScoped, Base):
    """One published snapshot of a flow. Never changed after it is written."""

    __tablename__ = "ivr_flow_versions"

    flow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ivr_flows.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int]
    definition: Mapped[dict[str, Any]]
    published_at: Mapped[datetime] = mapped_column(server_default=func.now())
    published_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    __table_args__ = (
        UniqueConstraint("flow_id", "version"),
        CheckConstraint("version > 0", name="version_positive"),
    )


class Prompt(UUIDPrimaryKey, Timestamps, TenantScoped, Base):
    """A recorded message of the tenant (welcome, menu, closed…), in up to three languages."""

    __tablename__ = "prompts"

    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(500), default="")

    __table_args__ = (UniqueConstraint("tenant_id", "name"),)


class PromptAudio(UUIDPrimaryKey, TenantScoped, Base):
    """The recording of a prompt in one language. The WAV file itself lives in the prompts
    volume that Asterisk reads (prompts.py): <tenant>/<language>/<prompt>.wav[16]."""

    __tablename__ = "prompt_audio"

    prompt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prompts.id", ondelete="CASCADE"), index=True
    )
    language: Mapped[Locale] = mapped_column(str_enum(Locale, "prompt_language"))
    sample_rate: Mapped[int]
    duration_ms: Mapped[int]
    size_bytes: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        UniqueConstraint("prompt_id", "language"),
        CheckConstraint("sample_rate IN (8000, 16000)", name="sample_rate_supported"),
        CheckConstraint("duration_ms > 0", name="duration_positive"),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="sha256_hex"),
    )


class OutboundRoute(UUIDPrimaryKey, Timestamps, TenantScoped, Base):
    """Dialled numbers matching `pattern` go out through the route's trunks, in order (failover
    to the next one when a trunk is unavailable or congested)."""

    __tablename__ = "outbound_routes"

    name: Mapped[str] = mapped_column(String(100))
    # Asterisk pattern without the leading "_", e.g. "0Z." or "00X." or "9X."
    pattern: Mapped[str] = mapped_column(String(32))
    strip_digits: Mapped[int] = mapped_column(default=0)
    prepend: Mapped[str] = mapped_column(String(16), default="")
    # Number shown to the called party; empty = the trunk's caller ID, else the caller's own.
    caller_id_number: Mapped[str | None] = mapped_column(String(32))
    priority: Mapped[int] = mapped_column(default=100)
    enabled: Mapped[bool] = mapped_column(default=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name"),
        CheckConstraint(r"pattern ~ '^[0-9XZN.!+*#\[\]-]{1,32}$'", name="pattern_chars"),
        CheckConstraint("strip_digits BETWEEN 0 AND 20", name="strip_range"),
        CheckConstraint("prepend ~ '^[+]?[0-9]{0,15}$'", name="prepend_digits"),
        CheckConstraint(
            "caller_id_number IS NULL OR caller_id_number ~ '^[+]?[0-9]{2,20}$'", name="cid_digits"
        ),
    )


class OutboundRouteTrunk(UUIDPrimaryKey, TenantScoped, Base):
    """Trunk `position` of a route (0 = first choice)."""

    __tablename__ = "outbound_route_trunks"

    route_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("outbound_routes.id", ondelete="CASCADE"), index=True
    )
    trunk_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("trunks.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int]

    __table_args__ = (
        UniqueConstraint("route_id", "position"),
        UniqueConstraint("route_id", "trunk_id"),
        CheckConstraint("position BETWEEN 0 AND 9", name="position_range"),
    )


class InboundRoute(UUIDPrimaryKey, Timestamps, TenantScoped, Base):
    """A called number (DID) arriving on a trunk -> an extension of the tenant, or a Mira Flow
    (task 1.4). `did` "*" = any number; `trunk_id` NULL = any trunk of the tenant."""

    __tablename__ = "inbound_routes"

    did: Mapped[str] = mapped_column(String(24))
    trunk_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("trunks.id", ondelete="CASCADE"), index=True
    )
    destination_number: Mapped[str | None] = mapped_column(String(16))
    # RESTRICT: a flow that answers a DID cannot be deleted from under it
    destination_flow_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ivr_flows.id", ondelete="RESTRICT"), index=True
    )
    enabled: Mapped[bool] = mapped_column(default=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "trunk_id", "did", postgresql_nulls_not_distinct=True),
        CheckConstraint("did = '*' OR did ~ '^[+]?[0-9]{1,20}$'", name="did_format"),
        CheckConstraint(
            "destination_number IS NULL OR destination_number ~ '^[0-9]{2,16}$'",
            name="destination_digits",
        ),
        CheckConstraint(
            "(destination_number IS NULL) <> (destination_flow_id IS NULL)",
            name="one_destination",
        ),
    )


class Voicemail(UUIDPrimaryKey, TenantScoped, Base):
    """A message left through a flow's voicemail node. The audio stays in Asterisk's
    recording spool (volume `voicemail`); Mira Core fetches it over ARI to play it."""

    __tablename__ = "voicemails"

    mailbox: Mapped[str] = mapped_column(String(16), index=True)  # extension number
    caller_number: Mapped[str] = mapped_column(String(64))
    call_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("calls.id", ondelete="SET NULL"), index=True
    )
    flow_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ivr_flows.id", ondelete="SET NULL")
    )
    recording_name: Mapped[str] = mapped_column(String(200), unique=True)  # ARI stored recording
    duration_seconds: Mapped[int]
    heard: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("ix_voicemails_tenant_mailbox", "tenant_id", "mailbox", "created_at"),
        CheckConstraint("duration_seconds >= 0", name="duration_positive"),
    )
