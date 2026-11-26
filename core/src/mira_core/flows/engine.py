"""The Mira Flow engine: runs one published flow on one call (task 1.4, ADR 0010).

A FlowRun owns a channel that entered the `mira-ivr` Stasis application. It walks the flow's
nodes, turning each into ARI requests, and reacts to the events Asterisk sends for the
channel (keys pressed, playbacks and recordings finished, hang-up) through `deliver()`.

Limits: 200 node steps and 30 minutes per call; any engine error hangs the call up cleanly.
Keys the caller types stay in memory: they are never logged or written to call events.
"""

import asyncio
import contextlib
import logging
import uuid
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from mira_core.flows.http_dip import DataDip, render
from mira_core.flows.schema import (
    Branch,
    Collect,
    FlowDefinition,
    Hangup,
    HttpRequest,
    Menu,
    Play,
    QueueNode,
    SetLanguage,
    SetVariable,
    TimeCondition,
    Transfer,
    Voicemail,
)
from mira_core.prompts import sound_uri

log = logging.getLogger(__name__)

MAX_STEPS = 200
MAX_SECONDS = 30 * 60
LANGUAGES = ("ar", "en", "fr")
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


class Ari(Protocol):
    async def answer(self, channel: str) -> None: ...
    async def play(self, channel: str, media: str, lang: str, playback_id: str) -> None: ...
    async def stop_playback(self, playback_id: str) -> None: ...
    async def set_variable(self, channel: str, variable: str, value: str) -> None: ...
    async def continue_in_dialplan(self, channel: str, context: str, extension: str) -> None: ...
    async def hangup(self, channel: str) -> None: ...
    async def record(self, channel: str, name: str, max_seconds: int) -> None: ...


class HungUp(Exception):
    """The caller is gone (hang-up or the channel left Stasis)."""


@dataclass
class FlowContext:
    tenant_id: uuid.UUID
    flow_id: uuid.UUID
    version: int
    dialplan_context: str  # t_<tenant>: where transfers continue
    timezone: str
    default_language: str
    # prompt id -> languages it has a recording in
    prompts: dict[uuid.UUID, set[str]] = field(default_factory=dict)
    # queue id -> its number in the dialplan (task 1.5)
    queue_numbers: dict[uuid.UUID, str] = field(default_factory=dict)


@dataclass
class Outcome:
    kind: str  # transfer | queue | voicemail | hangup | caller_hangup | error | limit
    last_node: str = ""
    detail: str = ""


Journal = Callable[[str, dict[str, Any]], Awaitable[None]]
VoicemailSaver = Callable[[str, str, int], Awaitable[None]]  # mailbox, recording name, seconds
Clock = Callable[[ZoneInfo], datetime]


async def _no_journal(_kind: str, _data: dict[str, Any]) -> None:
    return None


class FlowRun:
    def __init__(
        self,
        ari: Ari,
        channel: dict[str, Any],
        flow: FlowDefinition,
        ctx: FlowContext,
        *,
        dip: DataDip | None = None,
        journal: Journal = _no_journal,
        save_voicemail: VoicemailSaver | None = None,
        clock: Clock = lambda tz: datetime.now(tz),
        call_id: str = "",
    ) -> None:
        self.ari = ari
        self.channel = str(channel["id"])
        self.flow = flow
        self.ctx = ctx
        self.dip = dip or DataDip()
        self.journal = journal
        self.save_voicemail = save_voicemail
        self.clock = clock
        self.events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.digits: deque[str] = deque()
        self.hung_up = False
        self.language = ctx.default_language if ctx.default_language in LANGUAGES else "en"
        self.variables: dict[str, str] = {
            "caller_number": str((channel.get("caller") or {}).get("number") or ""),
            "called_number": str((channel.get("dialplan") or {}).get("exten") or ""),
            "language": self.language,
            "call_id": call_id,
        }

    # ------------------------------------------------------------------ events in

    def deliver(self, event: dict[str, Any]) -> None:
        """Called by the worker for every event about this channel."""
        kind = event.get("type")
        if kind == "ChannelDtmfReceived":
            self.digits.append(str(event.get("digit", "")))
        elif kind in ("ChannelHangupRequest", "ChannelDestroyed", "StasisEnd"):
            self.hung_up = True
        self.events.put_nowait(event)

    async def _next_event(self, timeout: float | None) -> dict[str, Any] | None:
        if self.hung_up:
            raise HungUp
        try:
            event = await asyncio.wait_for(self.events.get(), timeout)
        except TimeoutError:
            return None
        if event.get("type") in ("ChannelHangupRequest", "ChannelDestroyed", "StasisEnd"):
            raise HungUp
        return event

    async def _wait_digit(self, timeout: float) -> str | None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while not self.digits:
            left = deadline - loop.time()
            if left <= 0:
                return None
            await self._next_event(left)
        return self.digits.popleft()

    # ------------------------------------------------------------------ media

    def _prompt_language(self, prompt: uuid.UUID) -> str:
        have = self.ctx.prompts.get(prompt, set())
        for lang in (self.language, self.ctx.default_language, *LANGUAGES):
            if lang in have:
                return lang
        return self.language

    async def _play(self, media: str, lang: str, interruptible: bool) -> None:
        """Play to the end, or (interruptible) until the caller presses a key."""
        if interruptible and self.digits:
            return  # typed ahead: skip the prompt
        playback = uuid.uuid4().hex
        await self.ari.play(self.channel, media, lang, playback)
        while True:
            event = await self._next_event(60)
            if event is None:
                return  # no PlaybackFinished within a minute: move on
            if (
                event.get("type") == "PlaybackFinished"
                and (event.get("playback") or {}).get("id") == playback
            ):
                return
            if interruptible and self.digits:
                await self.ari.stop_playback(playback)
                return

    async def play_prompt(self, prompt: uuid.UUID, interruptible: bool = False) -> None:
        lang = self._prompt_language(prompt)
        await self._play(sound_uri(self.ctx.tenant_id, prompt, lang), lang, interruptible)

    async def play_sound(self, name: str) -> None:
        await self._play(f"sound:{name}", self.language, False)

    # ------------------------------------------------------------------ the walk

    async def run(self) -> Outcome:
        await self.journal(
            "FlowStarted", {"flow": str(self.ctx.flow_id), "version": self.ctx.version}
        )
        try:
            outcome = await asyncio.wait_for(self._walk(), timeout=MAX_SECONDS)
        except HungUp:
            outcome = Outcome("caller_hangup", self._current)
        except TimeoutError:
            outcome = Outcome("limit", self._current, "30 minutes in the flow")
        except Exception as exc:  # never leave a caller in silence
            log.exception("flow %s failed on node %s", self.ctx.flow_id, self._current)
            outcome = Outcome("error", self._current, type(exc).__name__)
        if outcome.kind in ("error", "limit", "hangup") and not self.hung_up:
            with contextlib.suppress(Exception):
                await self.ari.hangup(self.channel)
        await self.journal(
            "FlowEnded",
            {
                "flow": str(self.ctx.flow_id),
                "outcome": outcome.kind,
                "node": outcome.last_node,
                "detail": outcome.detail,
            },
        )
        return outcome

    _current = ""

    async def _walk(self) -> Outcome:
        await self.ari.answer(self.channel)
        node_id = self.flow.start
        for _ in range(MAX_STEPS):
            self._current = node_id
            node = self.flow.nodes[node_id]
            await self.journal("FlowNode", {"node": node_id, "node_type": node.type})
            result = await self._step(node)
            if isinstance(result, Outcome):
                result.last_node = node_id
                return result
            node_id = result
        return Outcome("limit", node_id, f"{MAX_STEPS} steps")

    async def _step(self, node: Any) -> str | Outcome:
        if isinstance(node, Play):
            await self.play_prompt(node.prompt)
            return node.next
        if isinstance(node, Menu):
            return await self._menu(node)
        if isinstance(node, Collect):
            return await self._collect(node)
        if isinstance(node, TimeCondition):
            return node.open_next if self._is_open(node) else node.closed_next
        if isinstance(node, SetLanguage):
            self.language = self.variables["language"] = node.language
            await self.ari.set_variable(self.channel, "CHANNEL(language)", node.language)
            return node.next
        if isinstance(node, SetVariable):
            self.variables[node.variable] = render(node.value, self.variables)[:500]
            return node.next
        if isinstance(node, Branch):
            return self._branch(node)
        if isinstance(node, HttpRequest):
            found = await self.dip.call(node, self.variables)
            if found is None:
                return node.error_next
            self.variables.update(found)
            return node.next
        if isinstance(node, Transfer):
            await self.ari.continue_in_dialplan(
                self.channel, self.ctx.dialplan_context, node.number
            )
            return Outcome("transfer", detail=node.number)
        if isinstance(node, QueueNode):
            number = self.ctx.queue_numbers.get(node.queue)
            if not number:
                return Outcome("error", detail="queue has no number yet (task 1.5)")
            await self.ari.continue_in_dialplan(self.channel, self.ctx.dialplan_context, number)
            return Outcome("queue", detail=number)
        if isinstance(node, Voicemail):
            return await self._voicemail(node)
        if isinstance(node, Hangup):
            await self.ari.hangup(self.channel)
            return Outcome("hangup")
        raise ValueError(f"unknown node {node!r}")

    async def _menu(self, node: Menu) -> str:
        for attempt in range(node.retries + 1):
            last = attempt == node.retries
            await self.play_prompt(node.prompt, interruptible=True)
            digit = await self._wait_digit(node.timeout_seconds)
            if digit is None:
                if last:
                    return node.timeout_next or node.invalid_next
                continue
            if digit in node.options:
                return node.options[digit]
            if last:
                return node.invalid_next
            if node.invalid_prompt:
                await self.play_prompt(node.invalid_prompt)
        return node.invalid_next  # pragma: no cover (the loop always returns)

    async def _collect(self, node: Collect) -> str:
        await self.play_prompt(node.prompt, interruptible=True)
        typed = ""
        while len(typed) < node.max_digits:
            digit = await self._wait_digit(node.timeout_seconds)
            if digit is None:
                break
            if node.terminator and digit == node.terminator:
                break
            typed += digit
        if len(typed) < node.min_digits:
            return node.timeout_next
        self.variables[node.variable] = typed
        return node.next

    def _is_open(self, node: TimeCondition) -> bool:
        now = self.clock(ZoneInfo(node.timezone or self.ctx.timezone))
        if now.date() in node.holidays:
            return False
        day, moment = WEEKDAYS[now.weekday()], now.time().replace(tzinfo=None)
        return any(day in r.days and r.start <= moment < r.end for r in node.weekly)

    def _branch(self, node: Branch) -> str:
        value = self.variables.get(node.variable, "")
        for c in node.conditions:
            other = render(c.value, self.variables)
            if c.op == "eq" and value == other:
                return c.next
            if c.op == "ne" and value != other:
                return c.next
            if c.op == "contains" and other in value:
                return c.next
            if c.op == "empty" and not value:
                return c.next
            if c.op == "not_empty" and value:
                return c.next
            if c.op in ("gt", "lt"):
                try:
                    a, b = float(value), float(other)
                except ValueError:
                    continue
                if (c.op == "gt" and a > b) or (c.op == "lt" and a < b):
                    return c.next
        return node.default_next

    async def _voicemail(self, node: Voicemail) -> Outcome:
        if node.greeting:
            await self.play_prompt(node.greeting)
        else:
            await self.play_sound("vm-intro")
        name = f"vm-{self.ctx.tenant_id.hex}-{uuid.uuid4().hex}"
        await self.ari.record(self.channel, name, node.max_seconds)
        seconds, finished = 0, False
        try:
            while True:
                event = await self._next_event(node.max_seconds + 15)
                if event is None:
                    break
                rec = event.get("recording") or {}
                if rec.get("name") == name and event.get("type") in (
                    "RecordingFinished",
                    "RecordingFailed",
                ):
                    finished = event["type"] == "RecordingFinished"
                    seconds = int(rec.get("duration") or 0)
                    break
        except HungUp:
            # the caller hung up after speaking: Asterisk still closes the file and reports it
            finished, seconds = await self._recording_after_hangup(name)
        if finished and seconds > 0 and self.save_voicemail is not None:
            await self.save_voicemail(node.mailbox, name, seconds)
        if not self.hung_up:
            with contextlib.suppress(HungUp):
                await self.play_sound("vm-goodbye")
            await self.ari.hangup(self.channel)
        return Outcome("voicemail", detail=node.mailbox if finished else "nothing recorded")

    async def _recording_after_hangup(self, name: str) -> tuple[bool, int]:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 5
        while (left := deadline - loop.time()) > 0:
            try:
                event = await asyncio.wait_for(self.events.get(), left)
            except TimeoutError:
                break
            rec = event.get("recording") or {}
            if rec.get("name") == name and event.get("type") in (
                "RecordingFinished",
                "RecordingFailed",
            ):
                return event["type"] == "RecordingFinished", int(rec.get("duration") or 0)
        return False, 0
