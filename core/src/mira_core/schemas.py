"""Request and response bodies (Pydantic). Never expose password_hash or SIP HA1."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    IPvAnyAddress,
    SecretStr,
    StringConstraints,
    model_validator,
)

from mira_core.models import (
    CallDirection,
    CallDisposition,
    Locale,
    Role,
    SipTransport,
    TenantStatus,
    TrunkKind,
)


def _lower(v: str) -> str:
    return v.lower()


Email = Annotated[EmailStr, AfterValidator(_lower)]
Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", max_length=63)]
# Strong enough for staff accounts; the UI will add a strength meter (task 2.5).
Password = Annotated[str, StringConstraints(min_length=12, max_length=128)]


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 — OAuth2 token type, not a password
    expires_in: int


class TenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: Slug
    timezone: str = Field(default="Africa/Cairo", max_length=64)
    default_locale: Locale = Locale.AR
    max_concurrent_calls: int = Field(default=10, ge=0, le=10_000)
    monthly_spend_cap: Decimal | None = Field(default=None, ge=0)
    recording_retention_days: int = Field(default=90, ge=0, le=3650)


class TenantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    status: TenantStatus
    timezone: str
    default_locale: Locale
    max_concurrent_calls: int
    monthly_spend_cap: Decimal | None
    recording_retention_days: int
    created_at: datetime


class UserCreate(BaseModel):
    email: Email
    full_name: str = Field(min_length=1, max_length=200)
    password: Password
    role: Role
    locale: Locale = Locale.AR
    # Only platform admins choose the tenant; for tenant admins it is always their own.
    tenant_id: uuid.UUID | None = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID | None
    email: str
    full_name: str
    role: Role
    is_active: bool
    locale: Locale
    last_login_at: datetime | None
    created_at: datetime


ExtensionNumber = Annotated[str, StringConstraints(pattern=r"^[0-9]{2,16}$")]


class ExtensionCreate(BaseModel):
    number: ExtensionNumber
    display_name: str = Field(min_length=1, max_length=100)
    user_id: uuid.UUID | None = None
    webrtc: bool = True
    # Only platform admins choose the tenant; for tenant admins it is always their own.
    tenant_id: uuid.UUID | None = None


class ExtensionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    number: str
    display_name: str
    user_id: uuid.UUID | None
    sip_username: str
    sip_realm: str
    webrtc: bool
    enabled: bool
    created_at: datetime


class ExtensionCredentials(ExtensionRead):
    """Returned once, on create and on password rotation. The password is not stored."""

    sip_password: str
    # True = config files written and Asterisk/Kamailio reloaded; False = written, reload failed
    config_applied: bool | None = None


# ---- trunks and routes (task 1.2) ----

Hostname = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9.-]{1,253}$")]
SipUser = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9._+-]{1,128}$")]
PhoneNumber = Annotated[str, StringConstraints(pattern=r"^[+]?[0-9]{2,20}$")]
RoutePattern = Annotated[str, StringConstraints(pattern=r"^[0-9XZN.!+*#\[\]-]{1,32}$")]
Did = Annotated[str, StringConstraints(pattern=r"^(\*|[+]?[0-9]{1,20})$")]


def _carrier_password(v: SecretStr | None) -> SecretStr | None:
    # Goes into an Asterisk config file: no line breaks, NULs or surrounding spaces.
    if v is None:
        return v
    raw = v.get_secret_value()
    if not 1 <= len(raw) <= 128 or raw != raw.strip() or any(c in raw for c in "\r\n\x00"):
        raise ValueError("password: 1-128 characters, no line breaks or surrounding spaces")
    return v


CarrierPassword = Annotated[SecretStr, AfterValidator(_carrier_password)]


class TrunkBase(BaseModel):
    host: Hostname | None = None
    port: int = Field(default=5060, ge=1, le=65535)
    transport: SipTransport = SipTransport.UDP
    auth_username: SipUser | None = None
    from_domain: Hostname | None = None
    caller_id_number: PhoneNumber | None = None
    max_channels: int = Field(default=30, ge=1, le=10_000)
    inbound_ips: list[IPvAnyAddress] = Field(default_factory=list, max_length=32)
    enabled: bool = True


class TrunkCreate(TrunkBase):
    """sip_register: host = carrier registrar, auth_username + password required.
    sip_ip_auth: host = carrier proxy; calls come from inbound_ips (and host, if an IP).
    gsm_gateway: no host, no password: Mira generates the gateway's SIP account."""

    name: str = Field(min_length=1, max_length=100)
    kind: TrunkKind
    password: CarrierPassword | None = None
    tenant_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _kind_rules(self) -> "TrunkCreate":
        if self.kind is TrunkKind.GSM_GATEWAY:
            if self.password is not None or self.auth_username is not None:
                raise ValueError("a GSM gateway gets its SIP account from Mira")
        elif self.host is None:
            raise ValueError("host is required")
        if self.kind is TrunkKind.SIP_REGISTER and not (self.auth_username and self.password):
            raise ValueError("a registering trunk needs auth_username and password")
        return self


class TrunkUpdate(BaseModel):
    """Only the fields sent change. password: a new value replaces it; null removes it."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    host: Hostname | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    transport: SipTransport | None = None
    auth_username: SipUser | None = None
    from_domain: Hostname | None = None
    caller_id_number: PhoneNumber | None = None
    max_channels: int | None = Field(default=None, ge=1, le=10_000)
    inbound_ips: list[IPvAnyAddress] | None = Field(default=None, max_length=32)
    enabled: bool | None = None
    password: CarrierPassword | None = None


class TrunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    kind: TrunkKind
    host: str
    port: int
    transport: SipTransport
    auth_username: str | None
    from_domain: str | None
    caller_id_number: str | None
    max_channels: int
    inbound_ips: list[str]
    enabled: bool
    has_password: bool  # the password itself is never returned
    sip_username: str | None  # gsm_gateway: the account the gateway registers with
    created_at: datetime
    config_applied: bool | None = None


class TrunkCredentials(TrunkRead):
    """gsm_gateway only, returned once (create, password rotation): enter these in the gateway's
    SIP trunk settings. The password is not stored, only its digest hash."""

    sip_password: str
    sip_realm: str


class OutboundRouteBase(BaseModel):
    pattern: RoutePattern
    strip_digits: int = Field(default=0, ge=0, le=20)
    prepend: Annotated[str, StringConstraints(pattern=r"^[+]?[0-9]{0,15}$")] = ""
    caller_id_number: PhoneNumber | None = None
    priority: int = Field(default=100, ge=0, le=10_000)
    enabled: bool = True
    # In order: the first is tried first, the next on "unavailable" or "congestion".
    trunk_ids: list[uuid.UUID] = Field(min_length=1, max_length=10)


class OutboundRouteCreate(OutboundRouteBase):
    name: str = Field(min_length=1, max_length=100)
    tenant_id: uuid.UUID | None = None


class OutboundRouteUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    pattern: RoutePattern | None = None
    strip_digits: int | None = Field(default=None, ge=0, le=20)
    prepend: Annotated[str, StringConstraints(pattern=r"^[+]?[0-9]{0,15}$")] | None = None
    caller_id_number: PhoneNumber | None = None
    priority: int | None = Field(default=None, ge=0, le=10_000)
    enabled: bool | None = None
    trunk_ids: list[uuid.UUID] | None = Field(default=None, min_length=1, max_length=10)


class OutboundRouteRead(OutboundRouteBase):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    created_at: datetime
    config_applied: bool | None = None


class InboundRouteCreate(BaseModel):
    """The call goes to an extension (`destination_number`) or a Mira Flow
    (`destination_flow_id`, task 1.4) — exactly one of them."""

    did: Did  # "*" = any number
    trunk_id: uuid.UUID | None = None  # None = any trunk of the tenant
    destination_number: ExtensionNumber | None = None
    destination_flow_id: uuid.UUID | None = None
    enabled: bool = True
    tenant_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _one_destination(self) -> "InboundRouteCreate":
        if (self.destination_number is None) == (self.destination_flow_id is None):
            raise ValueError("give destination_number or destination_flow_id (one of them)")
        return self


class InboundRouteUpdate(BaseModel):
    """Setting one destination clears the other."""

    did: Did | None = None
    destination_number: ExtensionNumber | None = None
    destination_flow_id: uuid.UUID | None = None
    enabled: bool | None = None

    @model_validator(mode="after")
    def _at_most_one(self) -> "InboundRouteUpdate":
        if self.destination_number is not None and self.destination_flow_id is not None:
            raise ValueError("give destination_number or destination_flow_id, not both")
        return self


class InboundRouteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    did: str
    trunk_id: uuid.UUID | None
    destination_number: str | None
    destination_flow_id: uuid.UUID | None
    enabled: bool
    created_at: datetime
    config_applied: bool | None = None


# ---- calls (task 1.3) ----


class CallRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    direction: CallDirection
    caller_number: str
    called_number: str
    started_at: datetime
    answered_at: datetime | None
    ended_at: datetime | None
    disposition: CallDisposition | None
    hangup_cause: int | None
    trunk_id: uuid.UUID | None
    agent_user_id: uuid.UUID | None


class CallEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    occurred_at: datetime
    type: str
    data: dict[str, object]


class CallDetail(CallRead):
    events: list[CallEventRead]


class LiveCallRead(BaseModel):
    call_id: uuid.UUID
    tenant_id: uuid.UUID
    direction: CallDirection
    state: str
    caller_number: str
    called_number: str
    started_at: datetime
    answered_at: datetime | None
    trunk_id: uuid.UUID | None
    agent_user_id: uuid.UUID | None


class ClickToCall(BaseModel):
    """Ring one of the caller's extensions; when it answers, dial `number` from it."""

    number: Annotated[str, StringConstraints(pattern=r"^[+]?[0-9*#]{2,24}$")]
    # Default: the caller's own (first enabled) extension. Admins may name any of the tenant's.
    extension_id: uuid.UUID | None = None
