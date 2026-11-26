"""The Mira Flow engine against a fake Asterisk (task 1.4 stage 2): every node type, the
safety limits, and the data dip's address checks. The real Asterisk run is in
tests/integration/telephony/flow-calls.sh."""

import asyncio
import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest

from mira_core.flows import engine
from mira_core.flows.engine import FlowContext, FlowRun
from mira_core.flows.http_dip import DataDip, allowed
from mira_core.flows.schema import FlowDefinition

pytestmark = pytest.mark.anyio

T = uuid.UUID("11111111-2222-3333-4444-555555555555")
WELCOME, MENU, PIN, SORRY = (uuid.uuid4() for _ in range(4))


class FakeAsterisk:
    """Answers the engine's ARI calls like Asterisk: playbacks finish, keys get pressed."""

    def __init__(self, keys: dict[str, str] | None = None, record_seconds: int = 7) -> None:
        self.run: FlowRun | None = None
        self.calls: list[tuple[Any, ...]] = []
        self.keys = dict(keys or {})  # prompt id hex -> digits pressed while it plays
        self.record_seconds = record_seconds
        self.hang_up_on_record = False

    def _send(self, event: dict[str, Any]) -> None:
        assert self.run is not None
        asyncio.get_running_loop().call_soon(self.run.deliver, event)

    async def answer(self, channel: str) -> None:
        self.calls.append(("answer",))

    async def play(self, channel: str, media: str, lang: str, playback_id: str) -> None:
        self.calls.append(("play", media.rsplit("/", 1)[-1], lang))
        for digit in self.keys.pop(media.rsplit("/", 1)[-1], ""):
            self._send({"type": "ChannelDtmfReceived", "digit": digit, "channel": {"id": channel}})
        self._send(
            {
                "type": "PlaybackFinished",
                "playback": {"id": playback_id, "target_uri": f"channel:{channel}"},
            }
        )

    async def stop_playback(self, playback_id: str) -> None:
        self.calls.append(("stop",))

    async def set_variable(self, channel: str, variable: str, value: str) -> None:
        self.calls.append(("set", variable, value))

    async def continue_in_dialplan(self, channel: str, context: str, extension: str) -> None:
        self.calls.append(("continue", context, extension))

    async def hangup(self, channel: str) -> None:
        self.calls.append(("hangup",))

    async def record(self, channel: str, name: str, max_seconds: int) -> None:
        self.calls.append(("record", max_seconds))
        if self.hang_up_on_record:
            self._send({"type": "ChannelHangupRequest", "channel": {"id": channel}})
        self._send(
            {
                "type": "RecordingFinished",
                "recording": {
                    "name": name,
                    "duration": self.record_seconds,
                    "target_uri": f"channel:{channel}",
                },
            }
        )


def ctx(**kw: Any) -> FlowContext:
    values: dict[str, Any] = {
        "tenant_id": T,
        "flow_id": uuid.uuid4(),
        "version": 1,
        "dialplan_context": "t_" + T.hex,
        "timezone": "Africa/Cairo",
        "default_language": "ar",
        "prompts": {p: {"ar", "en"} for p in (WELCOME, MENU, PIN, SORRY)},
    }
    values.update(kw)
    return FlowContext(**values)


def define(start: str, **nodes: dict[str, Any]) -> FlowDefinition:
    return FlowDefinition.model_validate({"schema": "mira-flow/1", "start": start, "nodes": nodes})


async def run_flow(
    flow: FlowDefinition, fake: FakeAsterisk, c: FlowContext | None = None, **kw: Any
) -> tuple[engine.Outcome, list[tuple[str, dict[str, Any]]]]:
    journal: list[tuple[str, dict[str, Any]]] = []

    async def note(kind: str, data: dict[str, Any]) -> None:
        journal.append((kind, data))

    channel = {
        "id": "1.1",
        "caller": {"number": "+201000000001"},
        "dialplan": {"exten": "+20225550100"},
    }
    run = FlowRun(fake, channel, flow, c or ctx(), journal=note, **kw)
    fake.run = run
    outcome = await asyncio.wait_for(run.run(), timeout=10)
    return outcome, journal


MENU_FLOW = dict(
    welcome={"type": "play", "prompt": str(WELCOME), "next": "menu"},
    menu={
        "type": "menu",
        "prompt": str(MENU),
        "options": {"1": "sales", "2": "support"},
        "timeout_seconds": 1,
        "retries": 1,
        "invalid_prompt": str(SORRY),
        "invalid_next": "bye",
    },
    sales={"type": "transfer", "number": "1001"},
    support={"type": "transfer", "number": "1002"},
    bye={"type": "hangup"},
)


async def test_menu_key_pressed_during_the_prompt_transfers() -> None:
    fake = FakeAsterisk(keys={MENU.hex: "2"})
    outcome, journal = await run_flow(define("welcome", **MENU_FLOW), fake)
    assert outcome.kind == "transfer" and outcome.detail == "1002"
    assert fake.calls[0] == ("answer",)
    assert ("play", WELCOME.hex, "ar") in fake.calls  # tenant language
    assert fake.calls[-1] == ("continue", "t_" + T.hex, "1002")
    assert [d["node"] for k, d in journal if k == "FlowNode"] == ["welcome", "menu", "support"]
    assert journal[0][0] == "FlowStarted" and journal[-1][1]["outcome"] == "transfer"


async def test_menu_retries_then_gives_up() -> None:
    fake = FakeAsterisk(keys={MENU.hex: "9"})  # wrong key, then silence
    outcome, _ = await run_flow(define("welcome", **MENU_FLOW), fake)
    plays = [c[1] for c in fake.calls if c[0] == "play"]
    assert plays == [WELCOME.hex, MENU.hex, SORRY.hex, MENU.hex]
    assert outcome.kind == "hangup" and outcome.last_node == "bye"


async def test_collect_and_branch() -> None:
    flow = define(
        "pin",
        pin={
            "type": "collect",
            "prompt": str(PIN),
            "variable": "pin",
            "min_digits": 4,
            "max_digits": 6,
            "timeout_seconds": 1,
            "next": "check",
            "timeout_next": "bye",
        },
        check={
            "type": "branch",
            "variable": "pin",
            "conditions": [{"op": "eq", "value": "1234", "next": "ok"}],
            "default_next": "bye",
        },
        ok={"type": "transfer", "number": "1001"},
        bye={"type": "hangup"},
    )
    good, _ = await run_flow(flow, FakeAsterisk(keys={PIN.hex: "1234#"}))
    assert good.kind == "transfer"
    short, _ = await run_flow(flow, FakeAsterisk(keys={PIN.hex: "12#"}))
    assert short.kind == "hangup"  # fewer than min_digits


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (datetime(2026, 11, 29, 10, 30), "1001"),  # Sunday 10:30: open
        (datetime(2026, 11, 29, 17, 0), "1002"),  # 17:00 is closed (the range ends there)
        (datetime(2026, 11, 27, 10, 30), "1002"),  # Friday: closed
        (datetime(2026, 12, 25, 10, 30), "1002"),  # a holiday (a Friday anyway) closed
        (datetime(2026, 12, 24, 10, 30), "1002"),  # Thursday, but a holiday below
    ],
)
async def test_time_condition_uses_the_tenant_timezone(moment: datetime, expected: str) -> None:
    flow = define(
        "hours",
        hours={
            "type": "time",
            "weekly": [
                {"days": ["sun", "mon", "tue", "wed", "thu"], "from": "09:00", "to": "17:00"}
            ],
            "holidays": ["2026-12-24", "2026-12-25"],
            "open_next": "open",
            "closed_next": "closed",
        },
        open={"type": "transfer", "number": "1001"},
        closed={"type": "transfer", "number": "1002"},
    )
    seen: list[str] = []

    def clock(tz: ZoneInfo) -> datetime:
        seen.append(str(tz))
        return moment.replace(tzinfo=tz)

    outcome, _ = await run_flow(flow, FakeAsterisk(), clock=clock)
    assert outcome.detail == expected and seen == ["Africa/Cairo"]


async def test_language_switch_and_prompt_fallback() -> None:
    flow = define(
        "fr",
        fr={"type": "language", "language": "fr", "next": "hello"},
        hello={"type": "play", "prompt": str(WELCOME), "next": "bye"},
        bye={"type": "hangup"},
    )
    fake = FakeAsterisk()
    # WELCOME exists only in English: French is asked for, the tenant default (ar) is missing too
    await run_flow(flow, fake, ctx(prompts={WELCOME: {"en"}}))
    assert ("set", "CHANNEL(language)", "fr") in fake.calls
    assert ("play", WELCOME.hex, "en") in fake.calls


async def test_voicemail_is_saved_even_when_the_caller_hangs_up() -> None:
    flow = define("vm", vm={"type": "voicemail", "mailbox": "1001", "max_seconds": 60})
    saved: list[tuple[str, str, int]] = []

    async def save(box: str, name: str, secs: int) -> None:
        saved.append((box, name, secs))

    fake = FakeAsterisk(record_seconds=9)
    outcome, _ = await run_flow(flow, fake, save_voicemail=save)
    assert outcome.kind == "voicemail" and ("record", 60) in fake.calls
    assert (
        saved
        and saved[0][0] == "1001"
        and saved[0][2] == 9
        and saved[0][1].startswith(f"vm-{T.hex}-")
    )
    assert ("play", "sound:vm-intro", "ar") in fake.calls and fake.calls[-1] == ("hangup",)

    saved.clear()
    gone = FakeAsterisk(record_seconds=4)
    gone.hang_up_on_record = True
    await run_flow(flow, gone, save_voicemail=save)
    assert [s[2] for s in saved] == [4]  # kept although the caller was already gone


async def test_caller_hangs_up_mid_flow() -> None:
    fake = FakeAsterisk()

    async def hang_up_soon() -> None:
        await asyncio.sleep(0.2)
        assert fake.run is not None
        fake.run.deliver({"type": "ChannelHangupRequest", "channel": {"id": "1.1"}})

    flow = define("menu", **{k: v for k, v in MENU_FLOW.items() if k != "welcome"})
    task = asyncio.create_task(hang_up_soon())
    outcome, journal = await run_flow(flow, fake)
    await task
    assert outcome.kind == "caller_hangup"
    assert ("hangup",) not in fake.calls  # nothing left to hang up
    assert journal[-1][1]["outcome"] == "caller_hangup"


async def test_endless_loops_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine, "MAX_STEPS", 20)
    flow = define(
        "a",
        a={"type": "set", "variable": "n", "value": "x", "next": "b"},
        b={
            "type": "branch",
            "variable": "n",
            "conditions": [{"op": "eq", "value": "x", "next": "a"}],
            "default_next": "a",
        },
    )
    fake = FakeAsterisk()
    outcome, _ = await run_flow(flow, fake)
    assert outcome.kind == "limit" and fake.calls[-1] == ("hangup",)


# ------------------------------------------------------------------ data dip

DIP_FLOW = dict(
    pin={
        "type": "collect",
        "prompt": str(PIN),
        "variable": "account",
        "timeout_seconds": 1,
        "next": "look",
        "timeout_next": "bye",
    },
    look={
        "type": "http",
        "url": "https://erp.example.com/api/method/mira.lookup?account={{account}}&caller={{caller_number}}",
        "headers": {"Authorization": "token abc"},
        "extract": {"vip": "message.vip", "name": "message.customer.0.name"},
        "next": "is_vip",
        "error_next": "bye",
    },
    is_vip={
        "type": "branch",
        "variable": "vip",
        "conditions": [{"op": "eq", "value": "1", "next": "vip"}],
        "default_next": "bye",
    },
    vip={"type": "transfer", "number": "1001"},
    bye={"type": "hangup"},
)


def erp(seen: list[httpx.Request], body: Any = None, status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            status,
            json=body
            if body is not None
            else {"message": {"vip": True, "customer": [{"name": "Nour"}]}},
        )

    return httpx.MockTransport(handler)


def resolver(addresses: list[str]):  # type: ignore[no-untyped-def]
    async def resolve(host: str, port: int) -> list[str]:
        return addresses

    return resolve


async def test_data_dip_goes_to_the_checked_address() -> None:
    seen: list[httpx.Request] = []
    dip = DataDip(resolver=resolver(["203.0.113.7"]), transport=erp(seen))
    outcome, _ = await run_flow(
        define("pin", **DIP_FLOW), FakeAsterisk(keys={PIN.hex: "5501#"}), dip=dip
    )
    assert outcome.kind == "transfer"  # vip -> 1001
    [req] = seen
    assert req.url.host == "203.0.113.7"  # connected to the resolved, checked IP...
    assert req.headers["host"] == "erp.example.com"  # ...but asking for the real name
    assert req.extensions["sni_hostname"] == "erp.example.com"
    assert req.url.params["account"] == "5501" and req.url.params["caller"] == "+201000000001"
    assert req.headers["authorization"] == "token abc"


@pytest.mark.parametrize(
    ("addresses", "allow_private"),
    [
        (["127.0.0.1"], True),  # every Mira service listens on loopback
        (["169.254.169.254"], True),  # cloud metadata
        (["::1"], True),
        (["203.0.113.7", "127.0.0.1"], True),  # one bad address is enough
        (["192.168.1.20"], False),  # Mira Cloud: no private ranges
        ([], True),
    ],
)
async def test_data_dip_refuses_internal_addresses(
    addresses: list[str], allow_private: bool
) -> None:
    seen: list[httpx.Request] = []
    dip = DataDip(allow_private=allow_private, resolver=resolver(addresses), transport=erp(seen))
    outcome, _ = await run_flow(
        define("pin", **DIP_FLOW), FakeAsterisk(keys={PIN.hex: "5501#"}), dip=dip
    )
    assert outcome.kind == "hangup" and seen == []  # error_next, and nothing was sent


@pytest.mark.parametrize(
    ("body", "status"),
    [({"message": {"vip": False}}, 200), ({"error": "x"}, 500), ("not json", 200)],
)
async def test_data_dip_failures_take_the_error_path(body: Any, status: int) -> None:
    seen: list[httpx.Request] = []
    transport = erp(seen, body, status)
    if body == "not json":
        transport = httpx.MockTransport(lambda r: httpx.Response(200, content=b"<html>"))
    dip = DataDip(resolver=resolver(["203.0.113.7"]), transport=transport)
    outcome, _ = await run_flow(
        define("pin", **DIP_FLOW), FakeAsterisk(keys={PIN.hex: "1#"}), dip=dip
    )
    assert outcome.kind == "hangup"


def test_lan_addresses_only_on_the_server_edition() -> None:
    assert allowed("192.168.1.20", allow_private=True)
    assert not allowed("192.168.1.20", allow_private=False)
    assert allowed("8.8.8.8", allow_private=False)
    assert not allowed("::ffff:127.0.0.1", allow_private=True)  # IPv4-mapped loopback
