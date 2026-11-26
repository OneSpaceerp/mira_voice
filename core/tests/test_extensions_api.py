import hashlib

import pytest
import sqlalchemy as sa
from httpx import AsyncClient

pytestmark = pytest.mark.anyio


@pytest.fixture
async def acme_admin(make_tenant, make_user, login) -> tuple[object, dict[str, str]]:
    t = make_tenant("acme")
    make_user("admin@acme.example.com", "tenant_admin", t)
    return t, await login("admin@acme.example.com")


async def test_create_gives_credentials_once_and_updates_asterisk(
    client: AsyncClient, acme_admin, sync_engine, dialplan_file, fake_ari
) -> None:
    tenant, h = acme_admin
    r = await client.post(
        "/api/v1/extensions", json={"number": "1001", "display_name": "Desk 1"}, headers=h
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["sip_username"] == "acme-1001"
    assert body["sip_realm"] == "mira"
    assert len(body["sip_password"]) >= 20
    assert body["config_applied"] is True
    # only the digest hash is stored, and it matches the password we were given
    with sync_engine.connect() as conn:
        ha1 = conn.execute(
            sa.text("SELECT sip_ha1 FROM extensions WHERE id = :i"), {"i": body["id"]}
        ).scalar_one()
    assert ha1 == hashlib.md5(f"acme-1001:mira:{body['sip_password']}".encode()).hexdigest()  # noqa: S324
    # Asterisk sees it at once (realtime view) and can dial it (generated dialplan + reload)
    with sync_engine.connect() as conn:
        assert (
            conn.execute(
                sa.text("SELECT count(*) FROM asterisk.ps_endpoints WHERE id = 'acme-1001'")
            ).scalar_one()
            == 1
        )
    assert f"[t_{tenant.hex}]" in dialplan_file.read_text()
    assert "exten => 1001,1,Gosub(mira-dial-extension,s,1(acme-1001))" in dialplan_file.read_text()
    assert "pbx_config.so" in fake_ari.reloads
    # the password never comes back
    listed = (await client.get("/api/v1/extensions", headers=h)).json()
    assert listed[0]["sip_username"] == "acme-1001"
    assert "sip_password" not in listed[0]


async def test_duplicate_number_conflicts(client: AsyncClient, acme_admin) -> None:
    _, h = acme_admin
    body = {"number": "1001", "display_name": "A"}
    assert (await client.post("/api/v1/extensions", json=body, headers=h)).status_code == 201
    assert (await client.post("/api/v1/extensions", json=body, headers=h)).status_code == 409


@pytest.mark.parametrize("number", ["1", "10a1", "1" * 17, "+201001"])
async def test_bad_numbers_rejected(client: AsyncClient, acme_admin, number: str) -> None:
    _, h = acme_admin
    r = await client.post(
        "/api/v1/extensions", json={"number": number, "display_name": "A"}, headers=h
    )
    assert r.status_code == 422


async def test_tenants_are_isolated(
    client: AsyncClient, acme_admin, make_tenant, make_user, login
) -> None:
    _, acme = acme_admin
    other = make_tenant("other")
    make_user("admin@other.example.com", "tenant_admin", other)
    other_agent = make_user("agent@other.example.com", "agent", other)
    h_other = await login("admin@other.example.com")
    ext = (
        await client.post(
            "/api/v1/extensions", json={"number": "1001", "display_name": "A"}, headers=acme
        )
    ).json()
    # same number in another tenant is fine, and gets its own SIP user
    r = await client.post(
        "/api/v1/extensions", json={"number": "1001", "display_name": "B"}, headers=h_other
    )
    assert r.json()["sip_username"] == "other-1001"
    # the other tenant cannot see, rotate or delete acme's extension
    assert {
        e["sip_username"] for e in (await client.get("/api/v1/extensions", headers=h_other)).json()
    } == {"other-1001"}
    assert (
        await client.post(f"/api/v1/extensions/{ext['id']}/password", headers=h_other)
    ).status_code == 404
    assert (
        await client.delete(f"/api/v1/extensions/{ext['id']}", headers=h_other)
    ).status_code == 404
    # acme cannot attach another tenant's user to its extension
    r = await client.post(
        "/api/v1/extensions",
        json={"number": "1002", "display_name": "C", "user_id": str(other_agent)},
        headers=acme,
    )
    assert r.status_code == 404


async def test_rotate_password_changes_the_hash(
    client: AsyncClient, acme_admin, sync_engine
) -> None:
    _, h = acme_admin
    ext = (
        await client.post(
            "/api/v1/extensions", json={"number": "1001", "display_name": "A"}, headers=h
        )
    ).json()
    r = await client.post(f"/api/v1/extensions/{ext['id']}/password", headers=h)
    assert r.status_code == 200
    new = r.json()["sip_password"]
    assert new != ext["sip_password"]
    with sync_engine.connect() as conn:
        ha1 = conn.execute(
            sa.text("SELECT sip_ha1 FROM extensions WHERE id = :i"), {"i": ext["id"]}
        ).scalar_one()
    assert ha1 == hashlib.md5(f"acme-1001:mira:{new}".encode()).hexdigest()  # noqa: S324


async def test_delete_removes_it_everywhere(
    client: AsyncClient, acme_admin, sync_engine, dialplan_file
) -> None:
    _, h = acme_admin
    ext = (
        await client.post(
            "/api/v1/extensions", json={"number": "1001", "display_name": "A"}, headers=h
        )
    ).json()
    assert (await client.delete(f"/api/v1/extensions/{ext['id']}", headers=h)).status_code == 204
    with sync_engine.connect() as conn:
        assert conn.execute(sa.text("SELECT count(*) FROM asterisk.ps_endpoints")).scalar_one() == 0
    assert "exten => 1001," not in dialplan_file.read_text()


@pytest.mark.parametrize("role", ["supervisor", "agent"])
async def test_only_admins_manage_extensions(client, make_tenant, make_user, login, role) -> None:
    make_user("u@example.com", role, make_tenant())
    h = await login("u@example.com")
    assert (await client.get("/api/v1/extensions", headers=h)).status_code == 403
    r = await client.post(
        "/api/v1/extensions", json={"number": "1001", "display_name": "A"}, headers=h
    )
    assert r.status_code == 403


async def test_platform_admin_must_name_the_tenant(
    client: AsyncClient, make_tenant, make_user, login
) -> None:
    t = make_tenant("acme")
    make_user("root@example.com", "platform_admin", None)
    h = await login("root@example.com")
    body = {"number": "1001", "display_name": "A"}
    assert (await client.post("/api/v1/extensions", json=body, headers=h)).status_code == 422
    r = await client.post("/api/v1/extensions", json={**body, "tenant_id": str(t)}, headers=h)
    assert r.status_code == 201
