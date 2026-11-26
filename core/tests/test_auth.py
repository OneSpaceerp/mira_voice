from datetime import UTC, datetime, timedelta

import jwt
import pytest
import sqlalchemy as sa
from httpx import AsyncClient

pytestmark = pytest.mark.anyio


async def test_login_returns_token_and_me_works(client, make_tenant, make_user, login) -> None:
    t = make_tenant()
    make_user("agent@example.com", "agent", t)
    headers = await login("agent@example.com")
    r = await client.get("/api/v1/auth/me", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "agent@example.com"
    assert body["role"] == "agent"
    assert body["tenant_id"] == str(t)
    assert body["last_login_at"] is not None
    assert "password_hash" not in body


async def test_login_is_case_insensitive_on_email(client, make_tenant, make_user, login) -> None:
    make_user("boss@example.com", "tenant_admin", make_tenant())
    await login("  Boss@Example.COM ")


@pytest.mark.parametrize(
    ("email", "password"), [("agent@example.com", "wrong password!"), ("nobody@example.com", "x")]
)
async def test_bad_login_same_answer(
    client: AsyncClient, make_tenant, make_user, email: str, password: str
) -> None:
    make_user("agent@example.com", "agent", make_tenant())
    r = await client.post("/api/v1/auth/token", data={"username": email, "password": password})
    assert r.status_code == 401
    assert r.json()["detail"] == "Incorrect e-mail or password"


async def test_disabled_user_cannot_log_in(client, make_tenant, make_user, password) -> None:
    make_user("gone@example.com", "agent", make_tenant(), active=False)
    r = await client.post(
        "/api/v1/auth/token", data={"username": "gone@example.com", "password": password}
    )
    assert r.status_code == 401


async def test_suspended_tenant_cannot_log_in(client, make_tenant, make_user, password) -> None:
    make_user("a@example.com", "agent", make_tenant(status="suspended"))
    r = await client.post(
        "/api/v1/auth/token", data={"username": "a@example.com", "password": password}
    )
    assert r.status_code == 401


async def test_me_requires_token(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_tampered_token_rejected(client, make_tenant, make_user, login) -> None:
    make_user("a@example.com", "agent", make_tenant())
    headers = await login("a@example.com")
    header, payload, sig = headers["Authorization"].split()[1].split(".")
    forged_sig = sig[:-4] + ("AAAA" if not sig.endswith("AAAA") else "BBBB")
    r = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {header}.{payload}.{forged_sig}"}
    )
    assert r.status_code == 401


def _token(uid: object, tid: object, role: str, key: str, issued: datetime, minutes: int) -> str:
    claims = {
        "sub": str(uid),
        "tid": str(tid),
        "role": role,
        "type": "access",
        "iat": issued,
        "exp": issued + timedelta(minutes=minutes),
    }
    return jwt.encode(claims, key, algorithm="HS256")


async def test_expired_token_rejected(client, make_tenant, make_user) -> None:
    from mira_core.config import get_settings

    t = make_tenant()
    uid = make_user("a@example.com", "agent", t)
    key = get_settings().jwt_secret.get_secret_value()
    token = _token(uid, t, "agent", key, datetime.now(UTC) - timedelta(hours=2), 30)
    r = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


@pytest.mark.parametrize(("ahead", "status"), [(5, 200), (60, 401)])
async def test_small_clock_skew_tolerated(client, make_tenant, make_user, ahead, status) -> None:
    # A token issued a few seconds "in the future" (clock stepped back by NTP) still works;
    # one a minute ahead does not.
    from mira_core.config import get_settings

    t = make_tenant()
    uid = make_user("a@example.com", "agent", t)
    key = get_settings().jwt_secret.get_secret_value()
    token = _token(uid, t, "agent", key, datetime.now(UTC) + timedelta(seconds=ahead), 30)
    r = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == status


async def test_token_signed_with_other_key_rejected(client, make_tenant, make_user) -> None:
    t = make_tenant()
    uid = make_user("a@example.com", "agent", t)
    token = _token(
        uid,
        t,
        "platform_admin",
        "an-attacker-chosen-key-that-is-long-enough-123456",
        datetime.now(UTC),
        5,
    )
    r = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


async def test_account_changes_apply_to_existing_tokens(
    client, make_tenant, make_user, login, sync_engine
) -> None:
    t = make_tenant()
    uid = make_user("a@example.com", "tenant_admin", t)
    headers = await login("a@example.com")
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200

    def run(sql: str, **params: object) -> None:
        with sync_engine.begin() as conn:
            conn.execute(sa.text(sql), params)

    run("UPDATE users SET role = 'agent' WHERE id = :id", id=uid)  # demoted: old admin token stops
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401
    run("UPDATE users SET role = 'tenant_admin' WHERE id = :id", id=uid)
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200
    run("UPDATE tenants SET status = 'suspended' WHERE id = :id", id=t)  # whole tenant out at once
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401
