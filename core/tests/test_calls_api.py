"""Calls API (task 1.3): history and live view scoped by tenant and role, hang-up and
click-to-call through ARI (a fake ARI here; the real one in tests/integration)."""

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from httpx import AsyncClient

from mira_core.live import LiveCall, LiveStore

pytestmark = pytest.mark.anyio


@pytest.fixture
async def world(client: AsyncClient, make_tenant, make_user, login, sync_engine, live: LiveStore):
    from mira_core.deps import get_live
    from mira_core.main import app

    app.dependency_overrides[get_live] = lambda: live
    t = make_tenant("acme")
    other = make_tenant("other")
    ids = {
        "admin": make_user("admin@acme.example.com", "tenant_admin", t),
        "sup": make_user("sup@acme.example.com", "supervisor", t),
        "a1": make_user("a1@acme.example.com", "agent", t),
        "a2": make_user("a2@acme.example.com", "agent", t),
        "x": make_user("x@other.example.com", "tenant_admin", other),
        "root": make_user("root@example.com", "platform_admin", None),
    }
    exts = {}
    with sync_engine.begin() as conn:
        for number, user in (("1001", ids["a1"]), ("1002", ids["a2"])):
            exts[number] = conn.execute(
                sa.text(
                    "INSERT INTO extensions (tenant_id, number, user_id, display_name, sip_username, "
                    "sip_ha1, sip_realm, webrtc, enabled) VALUES (:t, :n, :u, :n, :s, :h, 'mira', "
                    "true, true) RETURNING id"
                ),
                {"t": t, "n": number, "u": user, "s": f"acme-{number}", "h": "a" * 32},
            ).scalar_one()
        calls = {}
        for key, agent, ended in (
            ("c1", ids["a1"], True),
            ("c2", ids["a2"], True),
            ("live", ids["a1"], False),
        ):
            calls[key] = conn.execute(
                sa.text(
                    "INSERT INTO calls (tenant_id, asterisk_linkedid, direction, caller_number, "
                    "called_number, started_at, ended_at, disposition, agent_user_id) VALUES "
                    "(:t, :l, 'internal', '1001', '1002', now() - interval '1 minute', "
                    "CASE WHEN :e THEN now() END, CASE WHEN :e THEN 'answered' END, :a) RETURNING id"
                ),
                {"t": t, "l": f"link-{key}", "e": ended, "a": agent},
            ).scalar_one()
        conn.execute(
            sa.text(
                "INSERT INTO call_events (tenant_id, call_id, type, data) VALUES "
                "(:t, :c, 'ChannelCreated', '{\"channel\": \"PJSIP/acme-1001-1\"}')"
            ),
            {"t": t, "c": calls["c1"]},
        )
    await live.put(
        LiveCall(
            call_id=str(calls["live"]),
            tenant_id=str(t),
            direction="internal",
            state="up",
            caller_number="1001",
            called_number="1002",
            started_at="2026-11-26T10:00:00+00:00",
            answered_at="2026-11-26T10:00:05+00:00",
            agent_user_id=str(ids["a1"]),
        ),
        "call.started",
    )
    headers = {}
    for name, email in (
        ("admin", "admin@acme.example.com"),
        ("sup", "sup@acme.example.com"),
        ("a1", "a1@acme.example.com"),
        ("a2", "a2@acme.example.com"),
        ("x", "x@other.example.com"),
        ("root", "root@example.com"),
    ):
        headers[name] = await login(email)
    yield {"tenant": t, "other": other, "ids": ids, "exts": exts, "calls": calls, "h": headers}
    app.dependency_overrides.pop(get_live, None)


async def ids_of(client: AsyncClient, h: dict[str, str], **params: Any) -> set[str]:
    r = await client.get("/api/v1/calls", headers=h, params=params)
    assert r.status_code == 200, r.text
    return {c["id"] for c in r.json()}


async def test_history_is_scoped_by_tenant_and_role(client: AsyncClient, world) -> None:
    c, h = world["calls"], world["h"]
    everyone = {str(c["c1"]), str(c["c2"]), str(c["live"])}
    assert await ids_of(client, h["admin"]) == everyone
    assert await ids_of(client, h["sup"]) == everyone
    assert await ids_of(client, h["a1"]) == {str(c["c1"]), str(c["live"])}  # only their own
    assert await ids_of(client, h["x"]) == set()  # another tenant
    assert await ids_of(client, h["root"], tenant_id=str(world["tenant"])) == everyone
    r = await client.get("/api/v1/calls", headers=h["root"])
    assert r.status_code == 422  # platform admins must say which tenant
    r = await client.get(
        "/api/v1/calls", headers=h["x"], params={"tenant_id": str(world["tenant"])}
    )
    assert r.status_code == 404


async def test_call_detail_has_its_events(client: AsyncClient, world) -> None:
    c, h = world["calls"], world["h"]
    r = await client.get(f"/api/v1/calls/{c['c1']}", headers=h["a1"])
    assert r.status_code == 200
    body = r.json()
    assert body["disposition"] == "answered"
    assert [e["type"] for e in body["events"]] == ["ChannelCreated"]
    # someone else's call is "not found", for an agent and for another tenant
    assert (await client.get(f"/api/v1/calls/{c['c2']}", headers=h["a1"])).status_code == 404
    assert (await client.get(f"/api/v1/calls/{c['c1']}", headers=h["x"])).status_code == 404


async def test_live_view(client: AsyncClient, world) -> None:
    h = world["h"]
    r = await client.get("/api/v1/calls/live", headers=h["sup"])
    assert r.status_code == 200
    [call] = r.json()
    assert call["state"] == "up" and call["call_id"] == str(world["calls"]["live"])
    assert (await client.get("/api/v1/calls/live", headers=h["a2"])).json() == []  # not theirs
    assert (await client.get("/api/v1/calls/live", headers=h["x"])).json() == []


async def test_hangup_a_live_call(client: AsyncClient, world, fake_ari) -> None:
    c, h = world["calls"], world["h"]
    fake_ari.active = [
        {"id": "9.1", "channelvars": {"CHANNEL(linkedid)": "link-live"}},
        {"id": "9.2", "channelvars": {"CHANNEL(linkedid)": "link-live"}},
        {"id": "8.1", "channelvars": {"CHANNEL(linkedid)": "someone-else"}},
    ]
    # an agent may not hang up somebody else's call; another tenant does not even see it
    assert (
        await client.post(f"/api/v1/calls/{c['live']}/hangup", headers=h["a2"])
    ).status_code == 404
    assert (
        await client.post(f"/api/v1/calls/{c['live']}/hangup", headers=h["x"])
    ).status_code == 404
    r = await client.post(f"/api/v1/calls/{c['live']}/hangup", headers=h["sup"])
    assert r.status_code == 202 and r.json() == {"channels": 2}
    assert fake_ari.hung_up == ["9.1", "9.2"]  # only that call's channels
    # an ended call cannot be hung up
    assert (
        await client.post(f"/api/v1/calls/{c['c1']}/hangup", headers=h["sup"])
    ).status_code == 409


async def test_click_to_call_rings_the_users_own_phone(
    client: AsyncClient, world, fake_ari
) -> None:
    h, t = world["h"], world["tenant"]
    r = await client.post("/api/v1/calls", headers=h["a1"], json={"number": "0225550199"})
    assert r.status_code == 202, r.text
    assert r.json()["extension"] == "1001"
    assert fake_ari.originated == [
        {
            "endpoint": "PJSIP/acme-1001",
            "context": "t_" + uuid.UUID(str(t)).hex,
            "extension": "0225550199",
            "caller_id": '"Call 0225550199" <1001>',
        }
    ]


async def test_click_to_call_rules(client: AsyncClient, world, fake_ari) -> None:
    h, exts = world["h"], world["exts"]
    # an agent cannot ring somebody else's phone
    r = await client.post(
        "/api/v1/calls", headers=h["a1"], json={"number": "1002", "extension_id": str(exts["1002"])}
    )
    assert r.status_code == 404
    # a tenant admin may name any of the tenant's extensions
    r = await client.post(
        "/api/v1/calls",
        headers=h["admin"],
        json={"number": "1001", "extension_id": str(exts["1002"])},
    )
    assert r.status_code == 202 and fake_ari.originated[-1]["endpoint"] == "PJSIP/acme-1002"
    # a user without an extension, a platform admin, and a bad number
    assert (
        await client.post("/api/v1/calls", headers=h["sup"], json={"number": "1001"})
    ).status_code == 404
    assert (
        await client.post("/api/v1/calls", headers=h["root"], json={"number": "1001"})
    ).status_code == 403
    for bad in ("12a4", "1", "1001,1", "1001)\n[x]"):
        r = await client.post("/api/v1/calls", headers=h["a1"], json={"number": bad})
        assert r.status_code == 422, bad
