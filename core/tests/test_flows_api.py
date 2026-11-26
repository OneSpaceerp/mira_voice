"""Flows and prompts API (task 1.4 stage 1): drafts, publishing, versions, rollback, and the
prompt library with real WAV uploads."""

import io
import math
import struct
import wave
from pathlib import Path

import pytest
import sqlalchemy as sa
from httpx import AsyncClient

pytestmark = pytest.mark.anyio


def wav(seconds: float = 1.0, rate: int = 8000, channels: int = 1, width: int = 2) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        frames = int(seconds * rate)
        if width == 2:
            samples = (
                int(8000 * math.sin(2 * math.pi * 440 * i / rate)) for i in range(frames * channels)
            )
            w.writeframes(b"".join(struct.pack("<h", s) for s in samples))
        else:
            w.writeframes(b"\x80" * frames * channels * width)
    return out.getvalue()


@pytest.fixture
async def acme(client: AsyncClient, make_tenant, make_user, login, sync_engine):
    t = make_tenant("acme")
    make_user("admin@acme.example.com", "tenant_admin", t)
    make_user("agent@acme.example.com", "agent", t)
    with sync_engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO extensions (tenant_id, number, display_name, sip_username, sip_ha1, "
                "sip_realm, webrtc, enabled) VALUES (:t, '1001', 'Desk', 'acme-1001', :h, 'mira', true, true)"
            ),
            {"t": t, "h": "a" * 32},
        )
    return t, await login("admin@acme.example.com")


async def make_prompt(
    client: AsyncClient, h: dict[str, str], name: str = "welcome", audio: bool = True
) -> str:
    r = await client.post("/api/v1/prompts", headers=h, json={"name": name})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    if audio:
        r = await client.put(
            f"/api/v1/prompts/{pid}/audio/ar",
            headers={**h, "Content-Type": "audio/wav"},
            content=wav(),
        )
        assert r.status_code == 200, r.text
    return pid


def simple_flow(prompt: str, mailbox: str = "1001") -> dict:
    return {
        "schema": "mira-flow/1",
        "start": "hello",
        "nodes": {
            "hello": {"type": "play", "prompt": prompt, "next": "menu"},
            "menu": {
                "type": "menu",
                "prompt": prompt,
                "options": {"1": "desk"},
                "invalid_next": "vm",
            },
            "desk": {"type": "transfer", "number": "1001"},
            "vm": {"type": "voicemail", "mailbox": mailbox},
        },
    }


# ------------------------------------------------------------------ prompts


async def test_prompt_upload_is_cleaned_and_stored(client: AsyncClient, acme, sync_engine) -> None:
    from mira_core.config import get_settings

    t, h = acme
    pid = await make_prompt(client, h, audio=False)
    raw = wav(2.0, rate=16000)
    r = await client.put(
        f"/api/v1/prompts/{pid}/audio/fr", headers={**h, "Content-Type": "audio/wav"}, content=raw
    )
    assert r.status_code == 200, r.text
    [audio] = r.json()["audio"]
    assert (audio["language"], audio["sample_rate"], audio["duration_ms"]) == ("fr", 16000, 2000)
    path = Path(get_settings().prompts_dir) / t.hex / "fr" / (pid.replace("-", "") + ".wav16")
    assert path.is_file() and path.stat().st_mode & 0o777 == 0o640
    with wave.open(str(path)) as w:  # what Asterisk will read
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 16000)
    # an 8 kHz upload replaces it: only one rate stays, so Asterisk plays the new one
    r = await client.put(
        f"/api/v1/prompts/{pid}/audio/fr",
        headers={**h, "Content-Type": "audio/wav"},
        content=wav(1.0),
    )
    assert r.json()["audio"][0]["sample_rate"] == 8000
    assert not path.exists() and path.with_suffix(".wav").is_file()
    r = await client.get(f"/api/v1/prompts/{pid}/audio/fr", headers=h)
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"


@pytest.mark.parametrize(
    "body",
    [
        wav(rate=44100),
        wav(channels=2),
        wav(width=1),
        b"RIFF0000WAVEnot really",
        b"ID3 this is an mp3",
    ],
)
async def test_unplayable_audio_is_refused(client: AsyncClient, acme, body: bytes) -> None:
    _, h = acme
    pid = await make_prompt(client, h, audio=False)
    r = await client.put(
        f"/api/v1/prompts/{pid}/audio/en", headers={**h, "Content-Type": "audio/wav"}, content=body
    )
    assert r.status_code == 422, r.text


async def test_oversized_upload_is_refused(client: AsyncClient, acme) -> None:
    _, h = acme
    pid = await make_prompt(client, h, audio=False)
    big = b"\x00" * (12 * 1024 * 1024 + 1)
    r = await client.put(
        f"/api/v1/prompts/{pid}/audio/en", headers={**h, "Content-Type": "audio/wav"}, content=big
    )
    assert r.status_code == 413


# ------------------------------------------------------------------ flows


async def test_draft_publish_rollback(client: AsyncClient, acme) -> None:
    _, h = acme
    prompt = await make_prompt(client, h)
    r = await client.post("/api/v1/flows", headers=h, json={"name": "Main line"})
    assert r.status_code == 201
    fid = r.json()["id"]
    assert (
        await client.post(f"/api/v1/flows/{fid}/publish", headers=h)
    ).status_code == 422  # empty

    r = await client.put(f"/api/v1/flows/{fid}", headers=h, json={"draft": simple_flow(prompt)})
    assert r.status_code == 200, r.text
    assert r.json()["report"] == {"errors": [], "warnings": []}
    r = await client.post(f"/api/v1/flows/{fid}/publish", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["published_version"] == 1

    changed = simple_flow(prompt)
    changed["nodes"]["desk"]["number"] = "1002"
    await client.put(f"/api/v1/flows/{fid}", headers=h, json={"draft": changed})
    assert (await client.post(f"/api/v1/flows/{fid}/publish", headers=h)).json()[
        "published_version"
    ] == 2

    versions = (await client.get(f"/api/v1/flows/{fid}/versions", headers=h)).json()
    assert [(v["version"], v["current"]) for v in versions] == [(2, True), (1, False)]
    r = await client.post(f"/api/v1/flows/{fid}/rollback", headers=h, json={"version": 1})
    assert r.status_code == 200 and r.json()["published_version"] == 1
    v1 = (await client.get(f"/api/v1/flows/{fid}/versions/1", headers=h)).json()
    assert v1["current"] and v1["definition"]["nodes"]["desk"]["number"] == "1001"
    # published versions never change: editing works on the draft
    r = await client.post(f"/api/v1/flows/{fid}/versions/1/edit", headers=h)
    assert r.json()["draft"]["nodes"]["desk"]["number"] == "1001"


async def test_publish_checks_the_tenants_data(client: AsyncClient, acme) -> None:
    _, h = acme
    silent = await make_prompt(client, h, "silent", audio=False)  # no recording
    fid = (
        await client.post(
            "/api/v1/flows",
            headers=h,
            json={"name": "F", "draft": simple_flow(silent, mailbox="1999")},
        )
    ).json()["id"]
    r = await client.post(f"/api/v1/flows/{fid}/publish", headers=h)
    assert r.status_code == 422
    errors = r.json()["detail"]["errors"]
    assert any("has no recording yet" in e for e in errors)
    assert any("mailbox 1999 is not an extension" in e for e in errors)


async def test_drafts_are_work_in_progress(client: AsyncClient, acme) -> None:
    """Drafts are saved even when nodes are unfinished (the builder saves as you go); every
    problem is reported per node, and such a draft can never be published."""
    _, h = acme
    fid = (await client.post("/api/v1/flows", headers=h, json={"name": "F"})).json()["id"]
    r = await client.put(
        f"/api/v1/flows/{fid}",
        headers=h,
        json={"draft": {"start": "x", "nodes": {"x": {"type": "exec", "cmd": "ls"}}}},
    )
    assert r.status_code == 200
    assert r.json()["report"]["errors"][0].startswith("x: type:")
    assert (await client.post(f"/api/v1/flows/{fid}/publish", headers=h)).status_code == 422
    # a new menu node from the builder: no prompt chosen, no links yet
    unfinished = {
        "start": "m",
        "nodes": {"m": {"type": "menu", "prompt": "", "options": {"1": ""}, "invalid_next": ""}},
    }
    r = await client.put(f"/api/v1/flows/{fid}", headers=h, json={"draft": unfinished})
    errors = r.json()["report"]["errors"]
    assert r.status_code == 200 and any(e.startswith("m: prompt:") for e in errors)
    assert any(e.startswith("m: options.1:") for e in errors)
    # size limits still hold
    huge = {"start": "a", "nodes": {f"n{i}": {"type": "hangup"} for i in range(201)}}
    assert (
        await client.put(f"/api/v1/flows/{fid}", headers=h, json={"draft": huge})
    ).status_code == 422
    # a valid but half-wired draft is saved, with its problems listed
    half = {"start": "a", "nodes": {"a": {"type": "language", "language": "fr", "next": "b"}}}
    r = await client.put(f"/api/v1/flows/{fid}", headers=h, json={"draft": half})
    assert r.status_code == 200
    assert r.json()["report"]["errors"] == ["a: goes to 'b', which does not exist"]


async def test_flows_and_prompts_are_tenant_private(
    client: AsyncClient, acme, make_tenant, make_user, login
) -> None:
    _, h = acme
    prompt = await make_prompt(client, h)
    fid = (
        await client.post(
            "/api/v1/flows", headers=h, json={"name": "F", "draft": simple_flow(prompt)}
        )
    ).json()["id"]
    other = make_tenant("other")
    make_user("admin@other.example.com", "tenant_admin", other)
    oh = await login("admin@other.example.com")
    assert (await client.get(f"/api/v1/flows/{fid}", headers=oh)).status_code == 404
    assert (await client.get("/api/v1/flows", headers=oh)).json() == []
    assert (await client.get(f"/api/v1/prompts/{prompt}/audio/ar", headers=oh)).status_code == 404
    # another tenant's prompt cannot be used in a flow
    ofid = (
        await client.post(
            "/api/v1/flows", headers=oh, json={"name": "F", "draft": simple_flow(prompt)}
        )
    ).json()["id"]
    r = await client.post(f"/api/v1/flows/{ofid}/publish", headers=oh)
    assert r.status_code == 422 and any("does not exist" in e for e in r.json()["detail"]["errors"])


async def test_agents_cannot_edit_flows(client: AsyncClient, acme, login) -> None:
    h = await login("agent@acme.example.com")
    assert (await client.get("/api/v1/flows", headers=h)).status_code == 403
    assert (await client.post("/api/v1/prompts", headers=h, json={"name": "x"})).status_code == 403
    assert (
        await client.get("/api/v1/flows/schema", headers=h)
    ).status_code == 200  # the format is public


async def test_a_published_prompt_cannot_be_deleted(client: AsyncClient, acme) -> None:
    _, h = acme
    prompt = await make_prompt(client, h)
    fid = (
        await client.post(
            "/api/v1/flows", headers=h, json={"name": "F", "draft": simple_flow(prompt)}
        )
    ).json()["id"]
    assert (await client.post(f"/api/v1/flows/{fid}/publish", headers=h)).status_code == 200
    assert (await client.delete(f"/api/v1/prompts/{prompt}", headers=h)).status_code == 409
    spare = await make_prompt(client, h, "spare")
    assert (await client.delete(f"/api/v1/prompts/{spare}", headers=h)).status_code == 204


async def test_inbound_routes_to_flows(client: AsyncClient, acme, dialplan_file) -> None:
    _, h = acme
    prompt = await make_prompt(client, h)
    fid = (
        await client.post(
            "/api/v1/flows",
            headers=h,
            json={"name": "F", "number": "7000", "draft": simple_flow(prompt)},
        )
    ).json()["id"]
    route = {"did": "+20225550100", "destination_flow_id": fid}
    # not published yet: refused, and the flow number is not in the dialplan
    assert (await client.post("/api/v1/inbound-routes", headers=h, json=route)).status_code == 422
    assert (await client.post(f"/api/v1/flows/{fid}/publish", headers=h)).status_code == 200
    flow_hex = fid.replace("-", "")
    assert f"exten => 7000,1,Stasis(mira-ivr,{flow_hex})" in dialplan_file.read_text()
    r = await client.post("/api/v1/inbound-routes", headers=h, json=route)
    assert r.status_code == 201, r.text
    assert f"exten => +20225550100,1,Stasis(mira-ivr,{flow_hex})" in dialplan_file.read_text()
    both = {"did": "+20225550101", "destination_flow_id": fid, "destination_number": "1001"}
    assert (await client.post("/api/v1/inbound-routes", headers=h, json=both)).status_code == 422
    neither = {"did": "+20225550102"}
    assert (await client.post("/api/v1/inbound-routes", headers=h, json=neither)).status_code == 422
    # a flow that answers a DID cannot be deleted; switching the route to an extension frees it
    assert (await client.delete(f"/api/v1/flows/{fid}", headers=h)).status_code == 409
    rid = r.json()["id"]
    r = await client.patch(
        f"/api/v1/inbound-routes/{rid}", headers=h, json={"destination_number": "1001"}
    )
    assert r.status_code == 200 and r.json()["destination_flow_id"] is None
    assert (await client.delete(f"/api/v1/flows/{fid}", headers=h)).status_code == 204


async def test_flow_number_cannot_shadow_an_extension(client: AsyncClient, acme) -> None:
    _, h = acme
    r = await client.post("/api/v1/flows", headers=h, json={"name": "F", "number": "1001"})
    assert r.status_code == 409
