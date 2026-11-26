"""Test fixtures: a throwaway PostgreSQL 16 (testcontainers), migrated with the real Alembic
migrations, emptied after every test. Needs Docker."""

import os
import secrets
import tempfile
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from testcontainers.community.postgres import PostgresContainer

if TYPE_CHECKING:
    from mira_core.live import LiveStore

CORE_DIR = Path(__file__).resolve().parents[1]
GENERATED_DIR = Path(tempfile.mkdtemp(prefix="mira-asterisk-generated-"))
KAMAILIO_DIR = Path(tempfile.mkdtemp(prefix="mira-kamailio-generated-"))
PROMPTS_DIR = Path(tempfile.mkdtemp(prefix="mira-prompts-"))
POSTGRES_IMAGE = "postgres:16.16-trixie"  # same major version as production


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    with PostgresContainer(POSTGRES_IMAGE, driver=None) as pg:
        url = pg.get_connection_url()  # postgresql://... ; Mira switches it to psycopg 3
        os.environ["MIRA_DATABASE_URL"] = url
        os.environ["MIRA_JWT_SECRET"] = secrets.token_hex(32)
        os.environ["MIRA_ENV"] = "test"
        os.environ["ASTERISK_DB_PASSWORD"] = secrets.token_hex(16)
        os.environ["MIRA_ASTERISK_GENERATED_DIR"] = str(GENERATED_DIR)
        os.environ["MIRA_KAMAILIO_GENERATED_DIR"] = str(KAMAILIO_DIR)
        os.environ["MIRA_PROMPTS_DIR"] = str(PROMPTS_DIR)
        os.environ["KAMAILIO_RPC_TOKEN"] = secrets.token_hex(16)
        os.environ["MIRA_DATA_KEY"] = Fernet.generate_key().decode()
        from mira_core.config import get_settings
        from mira_core.db import get_engine, get_sessionmaker

        get_settings.cache_clear()
        get_engine.cache_clear()
        get_sessionmaker.cache_clear()
        command.upgrade(alembic_config(url), "head")
        yield url


VALKEY_IMAGE = "valkey/valkey:9.1.4-trixie"  # same as production (deploy/docker-compose.yml)


@pytest.fixture(scope="session")
def valkey_url() -> Iterator[str]:
    from testcontainers.community.redis import RedisContainer

    with RedisContainer(VALKEY_IMAGE) as v:
        yield f"redis://{v.get_container_host_ip()}:{v.get_exposed_port(6379)}/0"


@pytest.fixture
async def live(valkey_url: str) -> AsyncIterator["LiveStore"]:
    """A LiveStore on the test Valkey, emptied before each test (one client per event loop)."""
    from redis.asyncio import Redis

    from mira_core.live import LiveStore

    redis = Redis.from_url(valkey_url, decode_responses=True)
    await redis.flushdb()
    yield LiveStore(redis)
    await redis.aclose()


def alembic_config(url: str) -> Config:
    cfg = Config(str(CORE_DIR / "alembic.ini"))
    cfg.attributes["url"] = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return cfg


@pytest.fixture
def alembic_cfg(database_url: str) -> Config:
    return alembic_config(database_url)


@pytest.fixture(scope="session")
def sync_engine(database_url: str) -> Iterator[sa.Engine]:
    engine = sa.create_engine(database_url.replace("postgresql://", "postgresql+psycopg://", 1))
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean_tables(request: pytest.FixtureRequest) -> Iterator[None]:
    yield
    if "sync_engine" in request.fixturenames or "client" in request.fixturenames:
        engine: sa.Engine = request.getfixturevalue("sync_engine")
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "TRUNCATE call_events, recordings, calls, queue_members, queues, ivr_flow_versions, "
                    "ivr_flows, prompt_audio, prompts, "
                    "inbound_routes, outbound_route_trunks, outbound_routes, trunks, extensions, users, tenants RESTART IDENTITY CASCADE"
                )
            )


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeAri:
    """Stands in for Asterisk's ARI: records the module reloads Mira Core asks for."""

    def __init__(self) -> None:
        self.reloads: list[str] = []
        self.active: list[dict[str, object]] = []  # what GET /channels returns
        self.hung_up: list[str] = []
        self.originated: list[dict[str, object]] = []

    async def reload_module(self, module: str) -> None:
        self.reloads.append(module)

    async def channels(self) -> list[dict[str, object]]:
        return list(self.active)

    async def hangup(self, channel_id: str) -> bool:
        found = any(c["id"] == channel_id for c in self.active)
        self.active = [c for c in self.active if c["id"] != channel_id]
        if found:
            self.hung_up.append(channel_id)
        return found

    async def originate(
        self, endpoint: str, context: str, extension: str, caller_id: str, timeout: int = 30
    ) -> dict[str, object]:
        self.originated.append(
            {
                "endpoint": endpoint,
                "context": context,
                "extension": extension,
                "caller_id": caller_id,
            }
        )
        return {"id": "1795000000.1", "name": endpoint + "-00000001"}


@pytest.fixture
def fake_ari() -> FakeAri:
    return FakeAri()


class FakeKamailio:
    """Stands in for Kamailio's JSON-RPC: records the commands Mira Core sends."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def call(self, method: str) -> object:
        self.calls.append(method)
        return None


@pytest.fixture
def fake_kamailio() -> FakeKamailio:
    return FakeKamailio()


def _remove_generated() -> None:
    for directory in (GENERATED_DIR, KAMAILIO_DIR):
        for f in directory.glob("*"):
            f.unlink(missing_ok=True)


@pytest.fixture
def dialplan_file(database_url: str) -> Path:
    return GENERATED_DIR / "extensions_mira.conf"


@pytest.fixture
def pjsip_file(database_url: str) -> Path:
    return GENERATED_DIR / "pjsip_mira.conf"


@pytest.fixture
def dispatcher_file(database_url: str) -> Path:
    return KAMAILIO_DIR / "dispatcher.list"


@pytest.fixture
async def client(
    sync_engine: sa.Engine, fake_ari: FakeAri, fake_kamailio: FakeKamailio
) -> AsyncIterator[AsyncClient]:
    from mira_core.deps import get_ari, get_kamailio
    from mira_core.main import app

    _remove_generated()
    app.dependency_overrides[get_ari] = lambda: fake_ari
    app.dependency_overrides[get_kamailio] = lambda: fake_kamailio
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
    _remove_generated()


# ---- data helpers (straight into the database, exposed as fixtures) ----

PASSWORD = "correct horse battery staple"


@pytest.fixture
def password() -> str:
    return PASSWORD


@pytest.fixture
def make_tenant(sync_engine: sa.Engine) -> Callable[..., uuid.UUID]:
    def _make(slug: str = "acme", status: str = "active") -> uuid.UUID:
        with sync_engine.begin() as conn:
            tenant_id: uuid.UUID = conn.execute(
                sa.text(
                    "INSERT INTO tenants (name, slug, status, timezone, default_locale, max_concurrent_calls, "
                    "recording_retention_days) VALUES (:n, :s, :st, 'Africa/Cairo', 'ar', 10, 90) RETURNING id"
                ),
                {"n": slug.title(), "s": slug, "st": status},
            ).scalar_one()
        return tenant_id

    return _make


@pytest.fixture
def make_user(sync_engine: sa.Engine) -> Callable[..., uuid.UUID]:
    from mira_core.security import hash_password

    hashed = hash_password(PASSWORD)  # Argon2 is slow on purpose: hash once per test

    def _make(email: str, role: str, tenant_id: uuid.UUID | None, active: bool = True) -> uuid.UUID:
        with sync_engine.begin() as conn:
            user_id: uuid.UUID = conn.execute(
                sa.text(
                    "INSERT INTO users (tenant_id, email, full_name, password_hash, role, is_active, locale) "
                    "VALUES (:t, :e, :n, :p, :r, :a, 'en') RETURNING id"
                ),
                {
                    "t": tenant_id,
                    "e": email,
                    "n": email.split("@")[0],
                    "p": hashed,
                    "r": role,
                    "a": active,
                },
            ).scalar_one()
        return user_id

    return _make


@pytest.fixture
def login(client: AsyncClient) -> Callable[..., Awaitable[dict[str, str]]]:
    async def _login(email: str, password: str = PASSWORD) -> dict[str, str]:
        r = await client.post("/api/v1/auth/token", data={"username": email, "password": password})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    return _login
