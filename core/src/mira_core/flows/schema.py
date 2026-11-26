"""Mira Flow v1: the JSON format of an IVR flow (task 1.4, ADR 0009).

A flow is a graph: `start` names the first node, every node names the node(s) that follow.
Nodes are a tagged union on `type`. Nothing in a flow is code: text fields that reach the
caller or a web service are templates with `{{variable}}` placeholders only.

    {
      "schema": "mira-flow/1",
      "start": "welcome",
      "nodes": {
        "welcome": {"type": "play", "prompt": "<prompt id>", "next": "hours"},
        "hours":   {"type": "time", "open_next": "menu", "closed_next": "closed",
                    "weekly": [{"days": ["sun","mon","tue","wed","thu"], "from": "09:00", "to": "17:00"}]},
        "menu":    {"type": "menu", "prompt": "<prompt id>",
                    "options": {"1": "sales", "2": "support"}, "invalid_next": "op"},
        ...
      }
    }
"""

import re
import uuid
from datetime import date, time
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

SCHEMA_ID = "mira-flow/1"
MAX_NODES = 200

NodeId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,39}$")]
VarName = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,31}$")]
Digit = Annotated[str, StringConstraints(pattern=r"^[0-9*#]$")]
PhoneNumber = Annotated[str, StringConstraints(pattern=r"^[+]?[0-9*#]{2,24}$")]
Language = Literal["ar", "en", "fr"]
Weekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# Variables every call has; flows add their own with collect / set / http.
BUILTIN_VARIABLES = frozenset({"caller_number", "called_number", "language", "call_id"})
PLACEHOLDER = re.compile(r"\{\{\s*([a-z][a-z0-9_]{0,31})\s*\}\}")
# anything template-engine-like that is left after removing {{name}}: braces, {% %}, {# #}
_ANY_BRACES = re.compile(r"\{\{|\}\}|\{%|%\}|\{#|#\}")


def _template(value: str) -> str:
    """Only {{name}} placeholders, nothing that looks like an expression."""
    stripped = PLACEHOLDER.sub("", value)
    if _ANY_BRACES.search(stripped):
        raise ValueError("templates may only contain {{variable}} placeholders")
    if any(c in value for c in "\r\n\x00"):
        raise ValueError("no line breaks in templates")
    return value


Template = Annotated[str, StringConstraints(max_length=1000), AfterValidator(_template)]


def template_variables(value: str) -> set[str]:
    return set(PLACEHOLDER.findall(value))


class _Node(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(default="", max_length=80)  # shown in the builder only
    # builder canvas position (ignored by the engine)
    x: float = 0
    y: float = 0


class Play(_Node):
    """Play a prompt, then go on."""

    type: Literal["play"]
    prompt: uuid.UUID
    next: NodeId


class Menu(_Node):
    """Play a prompt and wait for one key. Unknown keys and silence are retried, then
    `invalid_next` / `timeout_next` (or `invalid_next` for both)."""

    type: Literal["menu"]
    prompt: uuid.UUID
    options: dict[Digit, NodeId] = Field(min_length=1, max_length=12)
    timeout_seconds: int = Field(default=5, ge=1, le=30)
    retries: int = Field(default=2, ge=0, le=5)
    invalid_prompt: uuid.UUID | None = None
    invalid_next: NodeId
    timeout_next: NodeId | None = None


class Collect(_Node):
    """Collect digits (account number, PIN…) into a variable. Never written to call events."""

    type: Literal["collect"]
    prompt: uuid.UUID
    variable: VarName
    min_digits: int = Field(default=1, ge=1, le=32)
    max_digits: int = Field(default=16, ge=1, le=32)
    terminator: Literal["#", "*", ""] = "#"
    timeout_seconds: int = Field(default=8, ge=1, le=60)
    next: NodeId
    timeout_next: NodeId

    @model_validator(mode="after")
    def _range(self) -> "Collect":
        if self.min_digits > self.max_digits:
            raise ValueError("min_digits is larger than max_digits")
        if self.variable in BUILTIN_VARIABLES:
            raise ValueError(f"'{self.variable}' is a built-in variable")
        return self


class TimeRange(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    days: list[Weekday] = Field(min_length=1, max_length=7)
    start: time = Field(alias="from")
    end: time = Field(alias="to")

    @model_validator(mode="after")
    def _order(self) -> "TimeRange":
        if self.start >= self.end:
            raise ValueError("'from' must be before 'to' (split overnight hours in two ranges)")
        return self


class TimeCondition(_Node):
    """Open or closed now, in the tenant's timezone (or `timezone`)? Holidays are closed."""

    type: Literal["time"]
    timezone: str | None = Field(default=None, max_length=64)  # default: the tenant's
    weekly: list[TimeRange] = Field(min_length=1, max_length=28)
    holidays: list[date] = Field(default_factory=list, max_length=366)
    open_next: NodeId
    closed_next: NodeId


class SetLanguage(_Node):
    """Prompts from here on play in this language (Arabic, English, French)."""

    type: Literal["language"]
    language: Language
    next: NodeId


class SetVariable(_Node):
    type: Literal["set"]
    variable: VarName
    value: Template
    next: NodeId

    @field_validator("variable")
    @classmethod
    def _not_builtin(cls, v: str) -> str:
        if v in BUILTIN_VARIABLES:
            raise ValueError(f"'{v}' is a built-in variable")
        return v


class Condition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["eq", "ne", "gt", "lt", "contains", "empty", "not_empty"]
    value: Template = ""
    next: NodeId


class Branch(_Node):
    """The first condition that holds for `variable` wins, else `default_next`."""

    type: Literal["branch"]
    variable: VarName
    conditions: list[Condition] = Field(min_length=1, max_length=10)
    default_next: NodeId


class HttpRequest(_Node):
    """Data dip: call a web service (ERPNext, CRM…) and keep parts of its JSON answer.

    `extract` maps a variable to a path in the JSON answer, e.g. "message.customer_name" or
    "data.0.status". A failure (error status, timeout, not JSON) goes to `error_next`."""

    type: Literal["http"]
    method: Literal["GET", "POST"] = "GET"
    url: Template
    headers: dict[Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9-]{1,64}$")], Template] = (
        Field(default_factory=dict, max_length=10)
    )
    body: dict[Annotated[str, StringConstraints(max_length=64)], Template] = Field(
        default_factory=dict, max_length=20
    )
    timeout_seconds: float = Field(default=3, gt=0, le=5)
    extract: dict[
        VarName, Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_.-]{1,128}$")]
    ] = Field(default_factory=dict, max_length=10)
    next: NodeId
    error_next: NodeId

    @field_validator("url")
    @classmethod
    def _url(cls, v: str) -> str:
        # placeholders are allowed in the path and query only, never in scheme or host
        parts = urlsplit(PLACEHOLDER.sub("x", v))
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("the URL must be http:// or https:// with a host name")
        if "{" in urlsplit(v).netloc or parts.username or parts.password:
            raise ValueError("the host of a data dip must be fixed and carry no credentials")
        return v


class Transfer(_Node):
    """Leave the flow and ring a number of the tenant: an extension or, through the
    tenant's outbound routes, an outside number. Ends the flow."""

    type: Literal["transfer"]
    number: PhoneNumber


class QueueNode(_Node):
    """Put the caller in a queue (task 1.5). Ends the flow."""

    type: Literal["queue"]
    queue: uuid.UUID


class Voicemail(_Node):
    """Play a greeting and record a message for a mailbox (an extension number)."""

    type: Literal["voicemail"]
    mailbox: Annotated[str, StringConstraints(pattern=r"^[0-9]{2,16}$")]
    greeting: uuid.UUID | None = None
    max_seconds: int = Field(default=120, ge=5, le=600)


class Hangup(_Node):
    type: Literal["hangup"]


Node = Annotated[
    Play
    | Menu
    | Collect
    | TimeCondition
    | SetLanguage
    | SetVariable
    | Branch
    | HttpRequest
    | Transfer
    | QueueNode
    | Voicemail
    | Hangup,
    Field(discriminator="type"),
]


class FlowDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_id: Literal["mira-flow/1"] = Field(default="mira-flow/1", alias="schema")
    start: NodeId
    nodes: dict[NodeId, Node] = Field(min_length=1, max_length=MAX_NODES)


def next_ids(node: BaseModel) -> list[str]:
    """Every node id this node can go to."""
    out: list[str] = []
    for name in (
        "next",
        "invalid_next",
        "timeout_next",
        "open_next",
        "closed_next",
        "default_next",
        "error_next",
    ):
        value = getattr(node, name, None)
        if value:
            out.append(value)
    if isinstance(node, Menu):
        out.extend(node.options.values())
    if isinstance(node, Branch):
        out.extend(c.next for c in node.conditions)
    return out


def prompt_ids(node: BaseModel) -> list[uuid.UUID]:
    found = [getattr(node, n, None) for n in ("prompt", "invalid_prompt", "greeting")]
    return [p for p in found if isinstance(p, uuid.UUID)]
