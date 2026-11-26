"""FastAPI application. Run: uvicorn mira_core.main:app --host 127.0.0.1 --port 8000"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis

from mira_core import __version__
from mira_core.api import (
    auth,
    calls,
    extensions,
    flows,
    health,
    prompts,
    routes,
    tenants,
    trunks,
    users,
    voicemails,
)
from mira_core.asterisk_config import apply_config
from mira_core.config import get_settings
from mira_core.db import get_engine, get_sessionmaker

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()  # fail fast on missing / weak settings
    # Live call state (Valkey). Connections open lazily, so the API starts even if it is down.
    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)
    # Bring the generated dialplan in line with the database (e.g. after an upgrade).
    try:
        async with get_sessionmaker()() as session:
            await apply_config(session, settings)
    except Exception:  # noqa: BLE001 — never block the API from starting
        log.exception("could not apply the telephony config at startup")
    yield
    await app.state.redis.aclose()
    await get_engine().dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Mira Core API",
        version=__version__,
        description="Control plane of Mira Voice (NSD): tenants, users, telephony configuration, calls.",
        lifespan=lifespan,
    )
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(tenants.router)
    app.include_router(users.router)
    app.include_router(extensions.router)
    app.include_router(trunks.router)
    app.include_router(routes.outbound)
    app.include_router(routes.inbound)
    app.include_router(calls.router)
    app.include_router(prompts.router)
    app.include_router(flows.router)
    app.include_router(voicemails.router)
    return app


app = create_app()
