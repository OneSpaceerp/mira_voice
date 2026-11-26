"""Tenants and users (accounts, roles)."""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from mira_core.models.base import Base, Timestamps, UUIDPrimaryKey, str_enum


class TenantStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class Locale(StrEnum):
    AR = "ar"
    EN = "en"
    FR = "fr"


class Role(StrEnum):
    """platform_admin runs the whole installation (NSD / the on-prem IT team); the others
    belong to exactly one tenant."""

    PLATFORM_ADMIN = "platform_admin"
    TENANT_ADMIN = "tenant_admin"
    SUPERVISOR = "supervisor"
    AGENT = "agent"


class Tenant(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(63), unique=True)
    status: Mapped[TenantStatus] = mapped_column(
        str_enum(TenantStatus, "tenant_status"), default=TenantStatus.ACTIVE
    )
    timezone: Mapped[str] = mapped_column(String(64), default="Africa/Cairo")
    default_locale: Mapped[Locale] = mapped_column(
        str_enum(Locale, "tenant_locale"), default=Locale.AR
    )
    # Abuse and cost limits (CLAUDE.md rule 5: per-tenant call limits and spend caps)
    max_concurrent_calls: Mapped[int] = mapped_column(default=10)
    monthly_spend_cap: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    recording_retention_days: Mapped[int] = mapped_column(default=90)

    __table_args__ = (
        CheckConstraint("slug ~ '^[a-z0-9]([a-z0-9-]*[a-z0-9])?$'", name="slug_format"),
        CheckConstraint("max_concurrent_calls >= 0", name="max_calls_positive"),
        CheckConstraint("recording_retention_days >= 0", name="retention_positive"),
    )


class User(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "users"

    # NULL only for platform admins (enforced by ck_users_platform_admin_has_no_tenant)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), index=True
    )
    email: Mapped[str] = mapped_column(String(254), unique=True)  # stored lower-case
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(str_enum(Role, "user_role"))
    is_active: Mapped[bool] = mapped_column(default=True)
    locale: Mapped[Locale] = mapped_column(str_enum(Locale, "user_locale"), default=Locale.AR)
    last_login_at: Mapped[datetime | None]

    __table_args__ = (
        CheckConstraint(
            "(role = 'platform_admin') = (tenant_id IS NULL)", name="platform_admin_has_no_tenant"
        ),
        CheckConstraint("email = lower(email)", name="email_lowercase"),
    )
