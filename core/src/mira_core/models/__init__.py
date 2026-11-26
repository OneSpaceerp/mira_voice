"""Data model v1. Importing this package registers every table on Base.metadata (Alembic uses it)."""

from mira_core.models.base import Base
from mira_core.models.calls import Call, CallDirection, CallDisposition, CallEvent, Recording
from mira_core.models.telephony import (
    Extension,
    InboundRoute,
    IvrFlow,
    IvrFlowVersion,
    OutboundRoute,
    OutboundRouteTrunk,
    Prompt,
    PromptAudio,
    Queue,
    QueueMember,
    QueueStrategy,
    SipTransport,
    Trunk,
    TrunkKind,
    Voicemail,
)
from mira_core.models.tenancy import Locale, Role, Tenant, TenantStatus, User

__all__ = [
    "Base",
    "Call",
    "CallDirection",
    "CallDisposition",
    "CallEvent",
    "Extension",
    "InboundRoute",
    "IvrFlow",
    "IvrFlowVersion",
    "OutboundRoute",
    "OutboundRouteTrunk",
    "Locale",
    "Prompt",
    "PromptAudio",
    "Queue",
    "QueueMember",
    "QueueStrategy",
    "Recording",
    "Role",
    "SipTransport",
    "Tenant",
    "TenantStatus",
    "Trunk",
    "TrunkKind",
    "User",
    "Voicemail",
]
