import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.anyio


async def test_health_is_up(client: AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


async def test_ready_checks_database(client: AsyncClient) -> None:
    r = await client.get("/health/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "up"}


async def test_openapi_documents_the_api(client: AsyncClient) -> None:
    r = await client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    for p in (
        "/health",
        "/api/v1/auth/token",
        "/api/v1/auth/me",
        "/api/v1/tenants",
        "/api/v1/users",
    ):
        assert p in paths
