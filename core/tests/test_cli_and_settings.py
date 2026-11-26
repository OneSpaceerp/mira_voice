import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from mira_core.cli import main
from mira_core.config import Settings

pytestmark = pytest.mark.anyio


def test_weak_jwt_secret_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIRA_JWT_SECRET", "too-short")
    with pytest.raises(ValidationError, match="at least 32 characters"):
        Settings()  # type: ignore[call-arg]


def test_database_url_built_from_postgres_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MIRA_DATABASE_URL", raising=False)
    monkeypatch.setenv("MIRA_JWT_SECRET", "x" * 64)
    monkeypatch.setenv("POSTGRES_PASSWORD", "s3cr3t")
    url = Settings().sqlalchemy_url  # type: ignore[call-arg]
    assert url.drivername == "postgresql+psycopg"
    assert (url.host, url.port, url.username, url.database) == ("127.0.0.1", 5432, "mira", "mira")
    assert "s3cr3t" not in str(url)  # the password is masked when printed


async def test_create_admin_then_log_in(
    client: AsyncClient, capsys: pytest.CaptureFixture[str]
) -> None:
    # the CLI runs its own event loop, so call it from a worker thread
    import anyio.to_thread

    code = await anyio.to_thread.run_sync(
        main, ["create-admin", "--email", "IT@Example.com", "--name", "IT"]
    )
    assert code == 0
    out = capsys.readouterr().out
    password = out.strip().splitlines()[-1].rsplit(": ", 1)[1]
    r = await client.post(
        "/api/v1/auth/token", data={"username": "it@example.com", "password": password}
    )
    assert r.status_code == 200
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}
    )
    assert me.json()["role"] == "platform_admin"
    assert me.json()["tenant_id"] is None

    code = await anyio.to_thread.run_sync(main, ["create-admin", "--email", "it@example.com"])
    assert code == 1  # already exists


async def test_bootstrap_first_install_then_nothing(
    client: AsyncClient, capsys: pytest.CaptureFixture[str]
) -> None:
    import anyio.to_thread

    code = await anyio.to_thread.run_sync(
        main,
        ["bootstrap", "--email", "Owner@Example.com", "--company", "Acme", "--language", "en"],
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "Tenant created: Acme" in out
    password = out.strip().splitlines()[-1].rsplit(": ", 1)[1]
    r = await client.post(
        "/api/v1/auth/token", data={"username": "owner@example.com", "password": password}
    )
    assert r.status_code == 200
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    assert (me["role"], me["locale"]) == ("platform_admin", "en")
    tenants = (await client.get("/api/v1/tenants", headers=headers)).json()
    assert [(t["name"], t["slug"], t["default_locale"]) for t in tenants] == [("Acme", "main", "en")]

    # the installer runs it on every install: never a second admin, never a new password
    code = await anyio.to_thread.run_sync(main, ["bootstrap", "--email", "other@example.com"])
    assert code == 0
    out = capsys.readouterr().out
    assert "nothing changed" in out
    assert "Password" not in out
    tenants = (await client.get("/api/v1/tenants", headers=headers)).json()
    assert len(tenants) == 1


async def test_bootstrap_refuses_a_bad_email(capsys: pytest.CaptureFixture[str]) -> None:
    import anyio.to_thread

    code = await anyio.to_thread.run_sync(main, ["bootstrap", "--email", "admin@mira.local"])
    assert code == 2
    assert "Not a valid e-mail" in capsys.readouterr().err
