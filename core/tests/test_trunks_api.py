"""Trunks, outbound and inbound routes through the API (task 1.2): what is stored, what the
generated Asterisk / Kamailio files contain, and that tenants cannot see each other's."""

import hashlib
import uuid

import pytest
import sqlalchemy as sa
from httpx import AsyncClient

pytestmark = pytest.mark.anyio

WE = {
    "name": "WE",
    "kind": "sip_register",
    "host": "sip.we.example",
    "auth_username": "0225550000",
    "password": "carrier;secret",
    "from_domain": "we.example",
    "caller_id_number": "+20225550000",
}
IP_TRUNK = {
    "name": "Carrier B",
    "kind": "sip_ip_auth",
    "host": "198.51.100.20",
    "inbound_ips": ["198.51.100.21"],
}


@pytest.fixture
async def acme_admin(make_tenant, make_user, login) -> tuple[uuid.UUID, dict[str, str]]:
    t = make_tenant("acme")
    make_user("admin@acme.example.com", "tenant_admin", t)
    return t, await login("admin@acme.example.com")


async def test_carrier_password_is_encrypted_and_never_returned(
    client: AsyncClient, acme_admin, sync_engine, pjsip_file, dispatcher_file, fake_ari
) -> None:
    _, h = acme_admin
    r = await client.post("/api/v1/trunks", json=WE, headers=h)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["has_password"] is True and "password" not in body
    assert body["config_applied"] is True
    with sync_engine.connect() as conn:
        stored = conn.execute(
            sa.text("SELECT auth_secret_enc FROM trunks WHERE id = :i"), {"i": body["id"]}
        ).scalar_one()
    assert "carrier" not in stored  # Fernet token, not the password
    from mira_core import crypto

    assert crypto.decrypt(stored) == "carrier;secret"
    # Asterisk gets it (escaped) in the 0640 trunk file, with a registration
    conf = pjsip_file.read_text()
    trunk = "trunk_" + uuid.UUID(body["id"]).hex
    assert "password = carrier\\;secret" in conf
    assert f"[{trunk}-reg]" in conf
    assert pjsip_file.stat().st_mode & 0o777 == 0o640
    assert {"res_pjsip.so", "res_pjsip_outbound_registration.so"} <= set(fake_ari.reloads)
    # listing never shows it either
    listed = (await client.get("/api/v1/trunks", headers=h)).json()
    assert "password" not in listed[0] and "auth_secret_enc" not in listed[0]


@pytest.mark.parametrize(
    "bad",
    [
        {**WE, "password": None},  # registering trunk without password
        {**WE, "auth_username": None},
        {**WE, "password": "two\nlines"},
        {**WE, "host": "evil.example\n[x]"},
        {**IP_TRUNK, "inbound_ips": ["not-an-ip"]},
        {**IP_TRUNK, "host": None},
        {"name": "GW", "kind": "gsm_gateway", "password": "x"},  # Mira makes its password
    ],
)
async def test_invalid_trunks_rejected(client: AsyncClient, acme_admin, bad) -> None:
    _, h = acme_admin
    r = await client.post("/api/v1/trunks", json=bad, headers=h)
    assert r.status_code == 422, r.text


async def test_ip_trunk_goes_into_the_kamailio_list(
    client: AsyncClient, acme_admin, dispatcher_file, fake_kamailio
) -> None:
    _, h = acme_admin
    r = await client.post("/api/v1/trunks", json=IP_TRUNK, headers=h)
    assert r.status_code == 201, r.text
    trunk = "trunk_" + uuid.UUID(r.json()["id"]).hex
    listed = dispatcher_file.read_text()
    assert f"2 sip:198.51.100.21 32 0 duid={trunk};trunk={trunk}" in listed
    assert f"2 sip:198.51.100.20 32 0 duid={trunk};trunk={trunk}" in listed
    assert "dispatcher.reload" in fake_kamailio.calls


async def test_carrier_ip_belongs_to_one_trunk_only(
    client: AsyncClient, acme_admin, make_tenant, make_user, login
) -> None:
    _, h = acme_admin
    assert (await client.post("/api/v1/trunks", json=IP_TRUNK, headers=h)).status_code == 201
    other = make_tenant("other")
    make_user("admin@other.example.com", "tenant_admin", other)
    oh = await login("admin@other.example.com")
    same_ip = {**IP_TRUNK, "host": "sip.other.example", "inbound_ips": ["198.51.100.20"]}
    r = await client.post("/api/v1/trunks", json=same_ip, headers=oh)
    assert r.status_code == 409
    assert "acme" not in r.text.lower()


async def test_gsm_gateway_gets_a_one_time_sip_account(
    client: AsyncClient, acme_admin, sync_engine, pjsip_file, dispatcher_file
) -> None:
    _, h = acme_admin
    r = await client.post(
        "/api/v1/trunks", json={"name": "Yeastar", "kind": "gsm_gateway"}, headers=h
    )
    assert r.status_code == 201, r.text
    body = r.json()
    trunk = "trunk_" + uuid.UUID(body["id"]).hex
    assert body["sip_username"] == trunk and body["sip_realm"] == "mira"
    password = body["sip_password"]
    with sync_engine.connect() as conn:
        ha1 = conn.execute(
            sa.text("SELECT sip_ha1 FROM trunks WHERE id = :i"), {"i": body["id"]}
        ).scalar_one()
    assert ha1 == hashlib.md5(f"{trunk}:mira:{password}".encode()).hexdigest()  # noqa: S324
    assert f"password_digest = MD5:{ha1}" in pjsip_file.read_text()
    assert trunk not in dispatcher_file.read_text()  # identified by registration, not IP
    # rotation gives a new password and a new hash; GET never shows one
    r2 = await client.post(f"/api/v1/trunks/{body['id']}/password", headers=h)
    assert r2.status_code == 200 and r2.json()["sip_password"] != password
    assert (
        "sip_password" not in (await client.get(f"/api/v1/trunks/{body['id']}", headers=h)).json()
    )


async def test_routes_generate_the_dialplan(client: AsyncClient, acme_admin, dialplan_file) -> None:
    tenant, h = acme_admin
    we = (await client.post("/api/v1/trunks", json=WE, headers=h)).json()
    b = (await client.post("/api/v1/trunks", json=IP_TRUNK, headers=h)).json()
    ext = {"number": "1001", "display_name": "Reception"}
    assert (await client.post("/api/v1/extensions", json=ext, headers=h)).status_code == 201

    r = await client.post(
        "/api/v1/outbound-routes",
        json={
            "name": "Egypt national",
            "pattern": "0Z.",
            "trunk_ids": [we["id"], b["id"]],
        },
        headers=h,
    )
    assert r.status_code == 201, r.text
    assert r.json()["trunk_ids"] == [we["id"], b["id"]]
    r = await client.post(
        "/api/v1/inbound-routes",
        json={"did": "+20225550000", "trunk_id": we["id"], "destination_number": "1001"},
        headers=h,
    )
    assert r.status_code == 201, r.text

    plan = dialplan_file.read_text()
    we_id = "trunk_" + uuid.UUID(we["id"]).hex
    b_id = "trunk_" + uuid.UUID(b["id"]).hex
    # the trunk's caller ID is used when the route has none; trunk B keeps the caller's own
    assert (
        f"exten => _0Z.,1,Gosub(mira-outbound,s,1(${{EXTEN:0}},{we_id},+20225550000,{b_id},))"
        in plan
    )
    assert f"[t_{tenant.hex}_in_{uuid.UUID(we['id']).hex}]" in plan
    assert f"exten => +20225550000,1,Goto(t_{tenant.hex},1001,1)" in plan

    # failover order can be changed; deleting a trunk removes it from the route
    rid = (await client.get("/api/v1/outbound-routes", headers=h)).json()[0]["id"]
    r = await client.patch(
        f"/api/v1/outbound-routes/{rid}", json={"trunk_ids": [b["id"], we["id"]]}, headers=h
    )
    assert r.status_code == 200 and r.json()["trunk_ids"] == [b["id"], we["id"]]
    assert (await client.delete(f"/api/v1/trunks/{b['id']}", headers=h)).status_code == 204
    assert (await client.get("/api/v1/outbound-routes", headers=h)).json()[0]["trunk_ids"] == [
        we["id"]
    ]
    assert b_id not in dialplan_file.read_text()


async def test_inbound_route_needs_an_existing_extension(client: AsyncClient, acme_admin) -> None:
    _, h = acme_admin
    r = await client.post(
        "/api/v1/inbound-routes", json={"did": "*", "destination_number": "1999"}, headers=h
    )
    assert r.status_code == 422


@pytest.mark.parametrize("pattern", ["_0Z.", "0Z.;x", "0Z.\n[x]", "", "X" * 33])
async def test_bad_patterns_rejected(client: AsyncClient, acme_admin, pattern: str) -> None:
    _, h = acme_admin
    trunk = (await client.post("/api/v1/trunks", json=IP_TRUNK, headers=h)).json()
    r = await client.post(
        "/api/v1/outbound-routes",
        json={"name": "x", "pattern": pattern, "trunk_ids": [trunk["id"]]},
        headers=h,
    )
    assert r.status_code == 422


async def test_tenants_cannot_use_each_others_trunks(
    client: AsyncClient, acme_admin, make_tenant, make_user, login
) -> None:
    _, h = acme_admin
    acme_trunk = (await client.post("/api/v1/trunks", json=WE, headers=h)).json()
    other = make_tenant("other")
    make_user("admin@other.example.com", "tenant_admin", other)
    oh = await login("admin@other.example.com")
    assert (await client.get(f"/api/v1/trunks/{acme_trunk['id']}", headers=oh)).status_code == 404
    assert (await client.get("/api/v1/trunks", headers=oh)).json() == []
    r = await client.patch(f"/api/v1/trunks/{acme_trunk['id']}", json={"name": "x"}, headers=oh)
    assert r.status_code == 404
    r = await client.post(
        "/api/v1/outbound-routes",
        json={"name": "steal", "pattern": "0Z.", "trunk_ids": [acme_trunk["id"]]},
        headers=oh,
    )
    assert r.status_code == 404
    r = await client.post(
        "/api/v1/inbound-routes",
        json={"did": "*", "trunk_id": acme_trunk["id"], "destination_number": "1001"},
        headers=oh,
    )
    assert r.status_code == 404


async def test_password_update_and_removal(client: AsyncClient, acme_admin, pjsip_file) -> None:
    _, h = acme_admin
    trunk = (await client.post("/api/v1/trunks", json=IP_TRUNK, headers=h)).json()
    assert trunk["has_password"] is False
    r = await client.patch(
        f"/api/v1/trunks/{trunk['id']}",
        json={"auth_username": "acct", "password": "n3w-pass"},
        headers=h,
    )
    assert r.status_code == 200 and r.json()["has_password"] is True
    assert "password = n3w-pass" in pjsip_file.read_text()
    r = await client.patch(f"/api/v1/trunks/{trunk['id']}", json={"password": None}, headers=h)
    assert r.json()["has_password"] is False
    assert "n3w-pass" not in pjsip_file.read_text()
    # a registering trunk cannot lose its password
    we = (await client.post("/api/v1/trunks", json=WE, headers=h)).json()
    r = await client.patch(f"/api/v1/trunks/{we['id']}", json={"password": None}, headers=h)
    assert r.status_code == 422


@pytest.mark.parametrize("role", ["supervisor", "agent"])
async def test_only_admins_manage_trunks(client, make_tenant, make_user, login, role) -> None:
    t = make_tenant("acme")
    make_user("x@acme.example.com", role, t)
    h = await login("x@acme.example.com")
    assert (await client.get("/api/v1/trunks", headers=h)).status_code == 403
    assert (await client.post("/api/v1/trunks", json=WE, headers=h)).status_code == 403
    assert (await client.get("/api/v1/outbound-routes", headers=h)).status_code == 403
