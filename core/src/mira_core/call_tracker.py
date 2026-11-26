"""From ARI events to call records, call events and live state (task 1.3, ADR 0008).

A *call* is everything that shares an Asterisk linkedid: the caller's channel (the first one)
and every channel dialled for it. Asterisk sends us events for every channel (subscribeAll);
we keep the calls in memory while they are active and write:

    calls        one row per call: tenant, direction, numbers, trunk, agent, times, outcome
    call_events  a short, privacy-minded event trail (no DTMF: callers type card numbers)
    Valkey       the active calls per tenant + a pub/sub message on every change

Rules:
- tenant: the channel's `tenantid` (set on every Mira endpoint). Channels without one (the
  lab extensions) are not tracked.
- direction: inbound when the first channel is a trunk; outbound when a trunk channel is
  dialled later; internal otherwise.
- answered: when a *dialled* channel (not the caller's own) goes Up. A call Asterisk answers
  by itself (prompts, echo test) is not "answered" by anyone; IVR answers come with task 1.4.
- agent: the extension user who placed the call (internal / outbound) or answered it (inbound).
"""

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mira_core.live import LiveCall, LiveStore
from mira_core.models import Call, CallDirection, CallDisposition, CallEvent, Extension, Trunk

log = logging.getLogger(__name__)

# ari.conf `channelvars` makes Asterisk put this in every channel's JSON
LINKEDID_VAR = "CHANNEL(linkedid)"

# Events Asterisk sends us (ARI eventFilter) and the subset written to call_events
EVENT_TYPES = (
    "ChannelCreated",
    "ChannelStateChange",
    "ChannelDialplan",
    "Dial",
    "ChannelEnteredBridge",
    "ChannelLeftBridge",
    "ChannelHold",
    "ChannelUnhold",
    "ChannelHangupRequest",
    "ChannelDestroyed",
)
STORED_TYPES = frozenset(EVENT_TYPES) - {"ChannelDialplan", "ChannelHangupRequest"}
_NOT_A_NUMBER = {"", "s", "h", "i", "t"}

SessionFactory = Callable[[], AsyncSession]


def channel_endpoint(channel: dict[str, Any]) -> str:
    """'PJSIP/acme-1001-0000002a' -> 'acme-1001' (the PJSIP endpoint id)."""
    name = str(channel.get("name", ""))
    if not name.startswith("PJSIP/"):
        return ""
    return name[len("PJSIP/") :].rsplit("-", 1)[0]


def trunk_uuid(endpoint: str) -> uuid.UUID | None:
    if endpoint.startswith("trunk_") and len(endpoint) == 38:
        try:
            return uuid.UUID(endpoint[6:])
        except ValueError:
            return None
    return None


def linkedid(channel: dict[str, Any]) -> str:
    return str((channel.get("channelvars") or {}).get(LINKEDID_VAR) or channel.get("id", ""))


def event_time(event: dict[str, Any]) -> datetime:
    raw = event.get("timestamp")
    if isinstance(raw, str):
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
            try:
                return datetime.strptime(raw, fmt).astimezone(UTC)
            except ValueError:
                continue
    return datetime.now(UTC)


def _number(caller: Any) -> str:
    return str((caller or {}).get("number") or "")[:64]


@dataclass
class TrackedCall:
    call_id: uuid.UUID
    tenant_id: uuid.UUID
    linkedid: str
    first_channel: str
    live: LiveCall
    channels: set[str] = field(default_factory=set)
    answered: bool = False
    last_dialstatus: str = ""
    hangup_cause: int | None = None
    agent_user_id: uuid.UUID | None = None


def _disposition(call: TrackedCall) -> CallDisposition:
    if call.answered:
        return CallDisposition.ANSWERED
    if call.last_dialstatus == "BUSY" or call.hangup_cause == 17:
        return CallDisposition.BUSY
    if call.last_dialstatus in ("CHANUNAVAIL", "CONGESTION") or call.hangup_cause in (1, 3, 34, 38):
        return CallDisposition.FAILED
    return CallDisposition.NO_ANSWER


def _event_data(event: dict[str, Any]) -> dict[str, Any]:
    """What we keep of an event: who, what, why — never caller-typed digits or free text."""
    channel = event.get("channel") or event.get("peer") or {}
    data: dict[str, Any] = {"channel": channel.get("name", "")}
    if event["type"] == "ChannelCreated":
        data["caller"] = _number(channel.get("caller"))
    if event["type"] == "ChannelStateChange":
        data["state"] = channel.get("state", "")
    if event["type"] == "Dial":
        data["caller_channel"] = (event.get("caller") or {}).get("name", "")
        data["dialstatus"] = event.get("dialstatus", "")
    if event["type"] in ("ChannelEnteredBridge", "ChannelLeftBridge"):
        data["bridge"] = (event.get("bridge") or {}).get("id", "")
    if event["type"] == "ChannelDestroyed":
        data["cause"] = event.get("cause")
        data["cause_txt"] = str(event.get("cause_txt", ""))[:64]
    return data


class CallTracker:
    def __init__(self, sessions: SessionFactory, live: LiveStore) -> None:
        self.sessions = sessions
        self.live = live
        self.calls: dict[str, TrackedCall] = {}  # by linkedid
        self.by_channel: dict[str, str] = {}  # channel id -> linkedid

    # ------------------------------------------------------------------ events

    async def handle(self, event: dict[str, Any]) -> None:
        kind = event.get("type")
        if kind not in EVENT_TYPES:
            return
        # a Dial event is about its peer (the dialled channel); the others name their channel
        channel = (event.get("peer") if kind == "Dial" else event.get("channel")) or {}
        if not channel.get("id"):
            return
        call = self.calls.get(linkedid(channel))
        if call is None:
            if kind != "ChannelCreated":
                return
            call = await self._start(channel, event_time(event))
            if call is None:
                return
        async with self.sessions() as session:
            row = await session.get(Call, call.call_id)
            if row is None:  # deleted under us (tenant purge): stop tracking
                self._forget(call)
                return
            changed = await self._apply(session, call, row, kind, channel, event)
            if kind in STORED_TYPES:
                session.add(
                    CallEvent(
                        tenant_id=call.tenant_id,
                        call_id=call.call_id,
                        occurred_at=event_time(event),
                        type=kind,
                        data=_event_data(event),
                    )
                )
            ended = not call.channels
            if ended:
                row.ended_at = max(event_time(event), row.started_at)
                row.disposition = _disposition(call)
                row.hangup_cause = call.hangup_cause
            await session.commit()
        if ended:
            self._forget(call)
            await self.live.end(call.live)
        elif changed:
            await self.live.put(call.live, "call.updated")

    async def _start(self, channel: dict[str, Any], at: datetime) -> TrackedCall | None:
        """First channel of a new call (its id is the linkedid)."""
        tenant = channel.get("tenantid")
        if not tenant or linkedid(channel) != channel["id"]:
            return None  # untracked (lab) or a leg whose call we never saw start
        try:
            tenant_id = uuid.UUID(str(tenant))
        except ValueError:
            return None
        endpoint = channel_endpoint(channel)
        trunk_id = trunk_uuid(endpoint)
        async with self.sessions() as session:
            if trunk_id and await session.get(Trunk, trunk_id) is None:
                trunk_id = None
            agent = None if trunk_id else await self._extension_user(session, tenant_id, endpoint)
            exten = str((channel.get("dialplan") or {}).get("exten") or "")
            row = Call(
                tenant_id=tenant_id,
                asterisk_linkedid=channel["id"],
                direction=CallDirection.INBOUND if trunk_id else CallDirection.INTERNAL,
                caller_number=_number(channel.get("caller")),
                called_number="" if exten in _NOT_A_NUMBER else exten[:64],
                started_at=at,
                trunk_id=trunk_id,
                agent_user_id=agent,
            )
            session.add(row)
            await session.commit()
            call_id = row.id
        call = TrackedCall(
            call_id=call_id,
            tenant_id=tenant_id,
            linkedid=channel["id"],
            first_channel=channel["id"],
            agent_user_id=agent,
            live=LiveCall(
                call_id=str(call_id),
                tenant_id=str(tenant_id),
                direction=row.direction.value,
                state="ringing",
                caller_number=row.caller_number,
                called_number=row.called_number,
                started_at=at.isoformat(),
                trunk_id=str(trunk_id or ""),
                agent_user_id=str(agent or ""),
            ),
        )
        self.calls[call.linkedid] = call
        await self.live.put(call.live, "call.started")
        return call

    async def _apply(
        self,
        session: AsyncSession,
        call: TrackedCall,
        row: Call,
        kind: str,
        channel: dict[str, Any],
        event: dict[str, Any],
    ) -> bool:
        """Update the call from one event. Returns True when the live view changed."""
        changed = False
        cid = channel["id"]
        # first sight of a channel (normally ChannelCreated; any other event after a reconnect)
        if kind != "ChannelDestroyed" and cid not in call.channels:
            call.channels.add(cid)
            self.by_channel[cid] = call.linkedid
            if cid != call.first_channel:
                changed |= await self._new_leg(session, call, row, channel)
        if kind == "ChannelDialplan" and cid == call.first_channel and not row.called_number:
            exten = str((channel.get("dialplan") or {}).get("exten") or "")
            if exten not in _NOT_A_NUMBER:
                row.called_number = call.live.called_number = exten[:64]
                changed = True
        elif kind == "ChannelStateChange" and channel.get("state") == "Up":
            if cid != call.first_channel and not call.answered:
                call.answered = True
                row.answered_at = max(event_time(event), row.started_at)
                call.live.state = "up"
                call.live.answered_at = row.answered_at.isoformat()
                changed = True
                if call.agent_user_id is None:
                    agent = await self._extension_user(
                        session, call.tenant_id, channel_endpoint(channel)
                    )
                    if agent:
                        call.agent_user_id = row.agent_user_id = agent
                        call.live.agent_user_id = str(agent)
        elif kind == "Dial" and event.get("dialstatus"):
            call.last_dialstatus = str(event["dialstatus"])
        elif kind == "ChannelDestroyed":
            call.channels.discard(cid)
            self.by_channel.pop(cid, None)
            if cid == call.first_channel:
                cause = event.get("cause")
                call.hangup_cause = int(cause) if isinstance(cause, int) else None
        return changed

    async def _new_leg(
        self, session: AsyncSession, call: TrackedCall, row: Call, channel: dict[str, Any]
    ) -> bool:
        """A channel dialled for the call: a trunk leg makes an internal call outbound."""
        trunk_id = trunk_uuid(channel_endpoint(channel))
        if trunk_id and row.direction == CallDirection.INTERNAL:
            if await session.get(Trunk, trunk_id) is not None:
                row.trunk_id = trunk_id
                call.live.trunk_id = str(trunk_id)
            row.direction = CallDirection.OUTBOUND
            call.live.direction = CallDirection.OUTBOUND.value
            return True
        return False

    async def _extension_user(
        self, session: AsyncSession, tenant_id: uuid.UUID, endpoint: str
    ) -> uuid.UUID | None:
        if not endpoint or endpoint.startswith("trunk_"):
            return None
        user: uuid.UUID | None = await session.scalar(
            select(Extension.user_id).where(
                Extension.tenant_id == tenant_id, Extension.sip_username == endpoint
            )
        )
        return user

    async def republish(self) -> None:
        """Put every active call back into Valkey (after Valkey itself restarted empty)."""
        for call in list(self.calls.values()):
            await self.live.put(call.live, "call.updated")

    def _forget(self, call: TrackedCall) -> None:
        self.calls.pop(call.linkedid, None)
        for cid in list(call.channels):
            self.by_channel.pop(cid, None)

    # ------------------------------------------------------------------ restart

    async def reconcile(self, channels: list[dict[str, Any]]) -> None:
        """After (re)connecting: make the database and Valkey match the channels Asterisk has.

        Calls left open in the database whose channels are gone (ended while we were not
        listening) are closed now; calls in progress are picked up again."""
        now = datetime.now(UTC)
        groups: dict[str, list[dict[str, Any]]] = {}
        for ch in channels:
            if ch.get("tenantid"):
                groups.setdefault(linkedid(ch), []).append(ch)
        self.calls.clear()
        self.by_channel.clear()
        await self.live.clear()
        async with self.sessions() as session:
            open_rows = (await session.scalars(select(Call).where(Call.ended_at.is_(None)))).all()
            known = {r.asterisk_linkedid: r for r in open_rows}
            for stale in open_rows:
                if stale.asterisk_linkedid in groups:
                    continue
                stale.ended_at = max(now, stale.started_at)
                stale.disposition = (
                    CallDisposition.ANSWERED if stale.answered_at else CallDisposition.FAILED
                )
                session.add(
                    CallEvent(
                        tenant_id=stale.tenant_id,
                        call_id=stale.id,
                        occurred_at=now,
                        type="MiraReconciled",
                        data={"reason": "call ended while Mira Core was not listening"},
                    )
                )
            await session.commit()
        for lid, chans in groups.items():
            row = known.get(lid)
            first = next((c for c in chans if c["id"] == lid), None)
            if row is None:
                if first is None:
                    continue  # caller's channel already gone: nothing sensible to record
                created = await self._start(first, now)
                if created is None:
                    continue
                call = created
            else:
                call = TrackedCall(
                    call_id=row.id,
                    tenant_id=row.tenant_id,
                    linkedid=lid,
                    first_channel=lid,
                    answered=row.answered_at is not None,
                    agent_user_id=row.agent_user_id,
                    live=LiveCall(
                        call_id=str(row.id),
                        tenant_id=str(row.tenant_id),
                        direction=row.direction.value,
                        state="up" if row.answered_at else "ringing",
                        caller_number=row.caller_number,
                        called_number=row.called_number,
                        started_at=row.started_at.isoformat(),
                        answered_at=row.answered_at.isoformat() if row.answered_at else "",
                        trunk_id=str(row.trunk_id or ""),
                        agent_user_id=str(row.agent_user_id or ""),
                    ),
                )
                self.calls[lid] = call
                await self.live.put(call.live, "call.updated")
            for ch in chans:
                call.channels.add(ch["id"])
                self.by_channel[ch["id"]] = lid
        log.info("reconciled: %d active calls", len(self.calls))
