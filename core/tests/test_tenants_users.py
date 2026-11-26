import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.anyio

NEW_TENANT = {"name": "Nile Telecom", "slug": "nile-telecom"}
GOOD_PW = "a-long-password-1"


@pytest.fixture
async def platform(make_user, login) -> dict[str, str]:
    make_user("root@example.com", "platform_admin", None)
    return await login("root@example.com")


async def test_platform_admin_creates_and_lists_tenants(client: AsyncClient, platform) -> None:
    r = await client.post("/api/v1/tenants", json=NEW_TENANT, headers=platform)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["slug"] == "nile-telecom"
    assert body["default_locale"] == "ar"
    assert body["status"] == "active"
    r = await client.get("/api/v1/tenants", headers=platform)
    assert [t["slug"] for t in r.json()] == ["nile-telecom"]


async def test_duplicate_slug_conflicts(client: AsyncClient, platform) -> None:
    assert (
        await client.post("/api/v1/tenants", json=NEW_TENANT, headers=platform)
    ).status_code == 201
    assert (
        await client.post("/api/v1/tenants", json=NEW_TENANT, headers=platform)
    ).status_code == 409


@pytest.mark.parametrize("slug", ["Upper", "-start", "end-", "has space", "x" * 64])
async def test_bad_slug_rejected(client: AsyncClient, platform, slug: str) -> None:
    r = await client.post("/api/v1/tenants", json={"name": "x", "slug": slug}, headers=platform)
    assert r.status_code == 422


@pytest.mark.parametrize("role", ["tenant_admin", "supervisor", "agent"])
async def test_only_platform_admin_manages_tenants(
    client, make_tenant, make_user, login, role
) -> None:
    make_user("u@example.com", role, make_tenant())
    h = await login("u@example.com")
    assert (await client.get("/api/v1/tenants", headers=h)).status_code == 403
    assert (await client.post("/api/v1/tenants", json=NEW_TENANT, headers=h)).status_code == 403


async def test_tenant_is_invisible_to_other_tenants(client, make_tenant, make_user, login) -> None:
    mine, other = make_tenant("mine"), make_tenant("other")
    make_user("admin@mine.example.com", "tenant_admin", mine)
    h = await login("admin@mine.example.com")
    assert (await client.get(f"/api/v1/tenants/{mine}", headers=h)).status_code == 200
    assert (await client.get(f"/api/v1/tenants/{other}", headers=h)).status_code == 404


async def test_tenant_admin_sees_only_own_users(client, make_tenant, make_user, login) -> None:
    mine, other = make_tenant("mine"), make_tenant("other")
    make_user("admin@mine.example.com", "tenant_admin", mine)
    make_user("agent@mine.example.com", "agent", mine)
    make_user("agent@other.example.com", "agent", other)
    h = await login("admin@mine.example.com")
    for url in ("/api/v1/users", f"/api/v1/users?tenant_id={other}"):  # even when asking explicitly
        emails = {u["email"] for u in (await client.get(url, headers=h)).json()}
        assert emails == {"admin@mine.example.com", "agent@mine.example.com"}


async def test_tenant_admin_creates_users_in_own_tenant_only(
    client, make_tenant, make_user, login
) -> None:
    mine, other = make_tenant("mine"), make_tenant("other")
    make_user("admin@mine.example.com", "tenant_admin", mine)
    h = await login("admin@mine.example.com")
    new = {
        "email": "New.Agent@Mine.example.com",
        "full_name": "New Agent",
        "password": GOOD_PW,
        "role": "agent",
    }
    r = await client.post("/api/v1/users", json=new, headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["tenant_id"] == str(mine)
    assert r.json()["email"] == "new.agent@mine.example.com"
    assert "password" not in r.json()
    assert "password_hash" not in r.json()
    other_tenant = {**new, "email": "x@other.example.com", "tenant_id": str(other)}
    assert (await client.post("/api/v1/users", json=other_tenant, headers=h)).status_code == 404
    escalate = {**new, "email": "evil@example.com", "role": "platform_admin"}
    assert (await client.post("/api/v1/users", json=escalate, headers=h)).status_code == 403


async def test_platform_admin_user_rules(client: AsyncClient, platform, make_tenant) -> None:
    t = str(make_tenant())
    base = {"full_name": "X", "password": GOOD_PW}

    async def create(**fields: object) -> int:
        r = await client.post("/api/v1/users", json={**base, **fields}, headers=platform)
        return r.status_code

    assert await create(email="a@example.com", role="agent") == 422  # tenant required
    assert await create(email="a@example.com", role="agent", tenant_id=t) == 201
    assert (
        await create(email="p@example.com", role="platform_admin", tenant_id=t) == 422
    )  # no tenant allowed
    assert await create(email="p@example.com", role="platform_admin") == 201
    assert await create(email="a@example.com", role="agent", tenant_id=t) == 409  # duplicate e-mail


async def test_weak_password_rejected(client: AsyncClient, platform, make_tenant) -> None:
    body = {
        "email": "a@example.com",
        "full_name": "A",
        "password": "short",
        "role": "agent",
        "tenant_id": str(make_tenant()),
    }
    assert (await client.post("/api/v1/users", json=body, headers=platform)).status_code == 422


@pytest.mark.parametrize("role", ["supervisor", "agent"])
async def test_agents_and_supervisors_cannot_manage_users(
    client, make_tenant, make_user, login, role
) -> None:
    make_user("u@example.com", role, make_tenant())
    h = await login("u@example.com")
    assert (await client.get("/api/v1/users", headers=h)).status_code == 403
    body = {"email": "b@example.com", "full_name": "B", "password": GOOD_PW, "role": "agent"}
    assert (await client.post("/api/v1/users", json=body, headers=h)).status_code == 403
