"""CallTracker: ARI event sequences -> call rows, call events, live state (task 1.3).

The events are shaped like Asterisk 22's ARI JSON (Channel model: id, name, state, caller,
dialplan, tenantid, channelvars with CHANNEL(linkedid) from ari.conf)."""

import asyncio
import json
import uuid
from typing import Any

import pytest
import sqlalchemy as sa

from mira_core.call_tracker import CallTracker
from mira_core.db import get_sessionmaker
from mira_core.live import LiveStore, tenant_events_channel

pytestmark = pytest.mark.anyio


# ---------------------------------------------------------------- builders


def channel(
    cid: str,
    endpoint: str,
    tenant: uuid.UUID | None,
    linked: str,
    *,
    state: str = "Ring",
    caller: str = "1001",
    exten: str = "s",
    seq: str = "00000001",
) -> dict[str, Any]:
    return {
        "id": cid,
        "name": f"PJSIP/{endpoint}-{seq}",
        "state": state,
        "caller": {"name": "", "number": caller},
        "connected": {"name": "", "number": ""},
        "accountcode": "",
        "dialplan": {"context": "t_x", "exten": exten, "priority": 1},
        "creationtime": "2026-11-26T10:00:00.000+0000",
        "language": "en",
        "channelvars": {"CHANNEL(linkedid)": linked},
        **({"tenantid": str(tenant)} if tenant else {}),
    }


def ev(kind: str, second: int, **fields: Any) -> dict[str, Any]:
    return {
        "type": kind,
        "timestamp": f"2026-11-26T10:00:{second:02d}.000+0000",
        "application": "mira",
        **fields,
    }


def up(ch: dict[str, Any]) -> dict[str, Any]:
    return {**ch, "state": "Up"}


@pytest.fixture
def setup(sync_engine, make_tenant, make_user) -> dict[str, Any]:
    t = make_tenant("acme")
    u1 = make_user("a1@acme.example.com", "agent", t)
    u2 = make_user("a2@acme.example.com", "agent", t)
    trunk = uuid.uuid4()
    with sync_engine.begin() as conn:
        for number, user in (("1001", u1), ("1002", u2)):
            conn.execute(
                sa.text(
                    "INSERT INTO extensions (tenant_id, number, user_id, display_name, "
                    "sip_username, sip_ha1, sip_realm, webrtc, enabled) VALUES "
                    "(:t, :n, :u, :n, :s, :h, 'mira', true, true)"
                ),
                {"t": t, "n": number, "u": user, "s": f"acme-{number}", "h": "a" * 32},
            )
        conn.execute(
            sa.text(
                "INSERT INTO trunks (id, tenant_id, name, kind, host, port, transport, "
                "max_channels, enabled) VALUES (:i, :t, 'WE', 'sip_ip_auth', '203.0.113.5', "
                "5060, 'udp', 30, true)"
            ),
            {"i": trunk, "t": t},
        )
    return {"tenant": t, "u1": u1, "u2": u2, "trunk": trunk, "trunk_ep": "trunk_" + trunk.hex}


def rows(engine: sa.Engine, sql: str, **p: Any) -> list[sa.Row[Any]]:
    with engine.connect() as conn:
        return list(conn.execute(sa.text(sql), p))


async def feed(tracker: CallTracker, events: list[dict[str, Any]]) -> None:
    for e in events:
        await tracker.handle(e)


# ---------------------------------------------------------------- scenarios


async def test_internal_call_answered(setup, live: LiveStore, sync_engine) -> None:
    t = setup["tenant"]
    tracker = CallTracker(get_sessionmaker(), live)
    a = channel("1.1", "acme-1001", t, "1.1", caller="1001", exten="1002")
    b = channel("1.2", "acme-1002", t, "1.1", caller="1001", exten="s", seq="00000002")

    pubsub = live.redis.pubsub()
    await pubsub.subscribe(tenant_events_channel(t))
    await feed(
        tracker,
        [
            ev("ChannelCreated", 0, channel=a),
            ev("ChannelDialplan", 0, channel=a, dialplan_app="Gosub", dialplan_app_data="x"),
            ev("ChannelCreated", 1, channel=b),
            ev("Dial", 1, caller=a, peer=b, dialstatus="", dialstring="acme-1002"),
            ev("ChannelStateChange", 2, channel={**b, "state": "Ringing"}),
        ],
    )
    [live_call] = await live.list_tenant(t)
    assert live_call.state == "ringing" and live_call.called_number == "1002"

    await feed(
        tracker,
        [
            ev("ChannelStateChange", 5, channel=up(b)),
            ev("Dial", 5, caller=a, peer=up(b), dialstatus="ANSWER"),
            ev("ChannelStateChange", 5, channel=up(a)),
            ev("ChannelEnteredBridge", 5, channel=up(a), bridge={"id": "br1"}),
            ev("ChannelHangupRequest", 20, channel=up(a), cause=16),
            ev("ChannelDestroyed", 20, channel=up(a), cause=16, cause_txt="Normal Clearing"),
        ],
    )
    [live_call] = await live.list_tenant(t)  # one leg left: still live
    assert live_call.state == "up" and live_call.answered_at
    await tracker.handle(ev("ChannelDestroyed", 21, channel=up(b), cause=16, cause_txt="x"))
    assert await live.list_tenant(t) == []

    [call] = rows(sync_engine, "SELECT * FROM calls")
    assert call.direction == "internal"
    assert (call.caller_number, call.called_number) == ("1001", "1002")
    assert call.disposition == "answered" and call.hangup_cause == 16
    assert call.agent_user_id == setup["u1"]  # the extension user who placed it
    assert call.answered_at.second == 5 and call.ended_at.second == 21
    types = [r.type for r in rows(sync_engine, "SELECT type FROM call_events ORDER BY id")]
    assert types == [
        "ChannelCreated",
        "ChannelCreated",
        "Dial",
        "ChannelStateChange",
        "ChannelStateChange",
        "Dial",
        "ChannelStateChange",
        "ChannelEnteredBridge",
        "ChannelDestroyed",
        "ChannelDestroyed",
    ]  # no ChannelDialplan / HangupRequest noise

    # get_message returns None for the (ignored) subscribe confirmation too: read until quiet
    messages: list[str] = []
    deadline = asyncio.get_running_loop().time() + 2
    while asyncio.get_running_loop().time() < deadline:
        m = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.2)
        if m is not None:
            messages.append(json.loads(m["data"])["type"])
    assert messages[0] == "call.started" and messages[-1] == "call.ended"
    assert "call.updated" in messages
    await pubsub.aclose()


async def test_inbound_on_trunk_answered_by_agent(setup, live, sync_engine) -> None:
    t, ep = setup["tenant"], setup["trunk_ep"]
    tracker = CallTracker(get_sessionmaker(), live)
    k = channel("2.1", ep, t, "2.1", caller="+201000000001", exten="+20225550100")
    b = channel("2.2", "acme-1002", t, "2.1", seq="00000002")
    await feed(
        tracker,
        [
            ev("ChannelCreated", 0, channel=k),
            ev("ChannelCreated", 1, channel=b),
            ev("ChannelStateChange", 4, channel=up(b)),
            ev("ChannelDestroyed", 30, channel=up(k), cause=16, cause_txt="x"),
            ev("ChannelDestroyed", 30, channel=up(b), cause=16, cause_txt="x"),
        ],
    )
    [call] = rows(sync_engine, "SELECT * FROM calls")
    assert call.direction == "inbound" and call.trunk_id == setup["trunk"]
    assert call.called_number == "+20225550100" and call.caller_number == "+201000000001"
    assert call.disposition == "answered"
    assert call.agent_user_id == setup["u2"]  # the agent who answered


async def test_inbound_caller_gives_up_while_ringing(setup, live, sync_engine) -> None:
    t, ep = setup["tenant"], setup["trunk_ep"]
    tracker = CallTracker(get_sessionmaker(), live)
    k = channel("3.1", ep, t, "3.1", exten="+20225550100")
    b = channel("3.2", "acme-1002", t, "3.1", seq="00000002")
    await feed(
        tracker,
        [
            ev("ChannelCreated", 0, channel=k),
            ev("ChannelCreated", 1, channel=b),
            ev("ChannelStateChange", 1, channel={**b, "state": "Ringing"}),
            ev("ChannelDestroyed", 9, channel=k, cause=16, cause_txt="Normal Clearing"),
            ev("Dial", 9, caller=k, peer=b, dialstatus="CANCEL"),
            ev("ChannelDestroyed", 9, channel=b, cause=16, cause_txt="Normal Clearing"),
        ],
    )
    [call] = rows(sync_engine, "SELECT * FROM calls")
    assert call.disposition == "no_answer" and call.answered_at is None
    assert call.agent_user_id is None  # nobody answered


async def test_outbound_via_trunk_busy(setup, live, sync_engine) -> None:
    t, ep = setup["tenant"], setup["trunk_ep"]
    tracker = CallTracker(get_sessionmaker(), live)
    a = channel("4.1", "acme-1001", t, "4.1", exten="0225550199")
    k = channel("4.2", ep, t, "4.1", seq="00000002")
    await feed(
        tracker,
        [
            ev("ChannelCreated", 0, channel=a),
            ev("ChannelCreated", 1, channel=k),
            ev("Dial", 3, caller=a, peer=k, dialstatus="BUSY"),
            ev("ChannelDestroyed", 3, channel=k, cause=17, cause_txt="User busy"),
            ev("ChannelDestroyed", 4, channel=a, cause=17, cause_txt="User busy"),
        ],
    )
    [call] = rows(sync_engine, "SELECT * FROM calls")
    assert call.direction == "outbound" and call.trunk_id == setup["trunk"]
    assert call.disposition == "busy" and call.hangup_cause == 17


async def test_untracked_and_ignored_events(setup, live, sync_engine) -> None:
    tracker = CallTracker(get_sessionmaker(), live)
    lab = channel("5.1", "1001", None, "5.1")  # lab extension: no tenantid
    await feed(
        tracker,
        [
            ev("ChannelCreated", 0, channel=lab),
            ev("ChannelDtmfReceived", 1, channel=lab, digit="4"),
            ev("ChannelDestroyed", 2, channel=lab, cause=16, cause_txt="x"),
        ],
    )
    t = setup["tenant"]
    a = channel("6.1", "acme-1001", t, "6.1", exten="1002")
    await feed(
        tracker,
        [
            ev("ChannelCreated", 0, channel=a),
            ev("ChannelDtmfReceived", 1, channel=a, digit="4", duration_ms=100),
            ev("ChannelVarset", 1, channel=a, variable="CARD", value="4111111111111111"),
            ev("ChannelDestroyed", 2, channel=a, cause=16, cause_txt="x"),
        ],
    )
    assert len(rows(sync_engine, "SELECT id FROM calls")) == 1  # the lab call is not tracked
    dump = json.dumps([r.data for r in rows(sync_engine, "SELECT data FROM call_events")])
    assert "4111" not in dump and "digit" not in dump  # nothing a caller typed is kept
    [call] = rows(sync_engine, "SELECT disposition FROM calls")
    assert call.disposition == "no_answer"  # nobody else picked up


async def test_reconcile_after_a_restart(setup, live, sync_engine) -> None:
    t = setup["tenant"]
    tracker = CallTracker(get_sessionmaker(), live)
    # two calls start while the worker runs
    gone_a = channel("7.1", "acme-1001", t, "7.1", exten="1002")
    kept_a = channel("8.1", "acme-1002", t, "8.1", caller="1002", exten="1001")
    kept_b = channel("8.2", "acme-1001", t, "8.1", seq="00000003")
    await feed(
        tracker,
        [
            ev("ChannelCreated", 0, channel=gone_a),
            ev("ChannelCreated", 1, channel=kept_a),
            ev("ChannelCreated", 1, channel=kept_b),
            ev("ChannelStateChange", 2, channel=up(kept_b)),
        ],
    )
    # ...the worker restarts; meanwhile call 7.1 ended and a new call 9.1 began
    new = channel("9.1", "acme-1001", t, "9.1", exten="1002")
    fresh = CallTracker(get_sessionmaker(), live)
    await fresh.reconcile([kept_a, up(kept_b), new])

    by_link = {r.asterisk_linkedid: r for r in rows(sync_engine, "SELECT * FROM calls")}
    assert by_link["7.1"].ended_at is not None and by_link["7.1"].disposition == "failed"
    assert by_link["8.1"].ended_at is None and by_link["8.1"].answered_at is not None
    assert by_link["9.1"].ended_at is None
    reconciled = rows(sync_engine, "SELECT call_id FROM call_events WHERE type = 'MiraReconciled'")
    assert [r.call_id for r in reconciled] == [by_link["7.1"].id]
    live_ids = {c.call_id for c in await live.list_tenant(t)}
    assert live_ids == {str(by_link["8.1"].id), str(by_link["9.1"].id)}

    # the picked-up call ends normally afterwards
    await feed(
        fresh,
        [
            ev("ChannelDestroyed", 40, channel=up(kept_a), cause=16, cause_txt="x"),
            ev("ChannelDestroyed", 40, channel=up(kept_b), cause=16, cause_txt="x"),
        ],
    )
    [kept] = rows(sync_engine, "SELECT * FROM calls WHERE asterisk_linkedid = '8.1'")
    assert kept.disposition == "answered" and kept.ended_at is not None
    assert {c.call_id for c in await live.list_tenant(t)} == {str(by_link["9.1"].id)}
