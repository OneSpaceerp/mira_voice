"""Liveness and readiness probes (used by Docker healthchecks and monitoring)."""

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from mira_core import __version__
from mira_core.deps import SessionDep

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """The process is up (does not touch the database)."""
    return {"status": "ok", "version": __version__}


@router.get("/health/ready")
async def ready(session: SessionDep, response: Response) -> dict[str, str]:
    """Ready to serve: the database answers."""
    try:
        await session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 — any database failure means "not ready"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable", "database": "down"}
    return {"status": "ok", "database": "up"}
