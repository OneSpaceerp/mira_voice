"""Call routing (task 1.2, ADR 0007).

Outbound routes: a dialled pattern (Asterisk syntax without "_", e.g. "0Z." or "00X.") goes out
through an ordered list of the tenant's trunks; the next trunk is tried when one is unavailable
or congested. Digits can be stripped / prepended, and the caller ID set.

Inbound routes: a called number (DID, or "*" for any) arriving on a trunk (or on any trunk of
the tenant) rings an extension. Every change regenerates the dialplan.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from mira_core.asterisk_config import apply_config
from mira_core.deps import (
    AriDep,
    KamailioDep,
    SessionDep,
    SettingsDep,
    require_roles,
    scope_tenant,
)
from mira_core.models import (
    Extension,
    InboundRoute,
    IvrFlow,
    OutboundRoute,
    OutboundRouteTrunk,
    Role,
    Tenant,
    Trunk,
    User,
)
from mira_core.schemas import (
    InboundRouteCreate,
    InboundRouteRead,
    InboundRouteUpdate,
    OutboundRouteCreate,
    OutboundRouteRead,
    OutboundRouteUpdate,
)

outbound = APIRouter(prefix="/api/v1/outbound-routes", tags=["routing"])
inbound = APIRouter(prefix="/api/v1/inbound-routes", tags=["routing"])

TelephonyAdmin = Annotated[User, Depends(require_roles(Role.PLATFORM_ADMIN, Role.TENANT_ADMIN))]


async def _tenant(session: SessionDep, admin: User, requested: uuid.UUID | None) -> uuid.UUID:
    tenant_id = scope_tenant(admin, requested)
    if await session.get(Tenant, tenant_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant_id


async def _check_trunks(session: SessionDep, tenant_id: uuid.UUID, ids: list[uuid.UUID]) -> None:
    if len(set(ids)) != len(ids):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="A trunk is listed twice")
    found = set(
        await session.scalars(
            select(Trunk.id).where(Trunk.id.in_(ids), Trunk.tenant_id == tenant_id)
        )
    )
    if found != set(ids):  # another tenant's trunk is "not found", like a missing one
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Trunk not found")


async def _commit(session: SessionDep, what: str) -> None:
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"{what} already exists") from None


# ----------------------------------------------------------------------------- outbound


async def _route_read(
    session: SessionDep, route: OutboundRoute, applied: bool | None = None
) -> OutboundRouteRead:
    trunk_ids = list(
        await session.scalars(
            select(OutboundRouteTrunk.trunk_id)
            .where(OutboundRouteTrunk.route_id == route.id)
            .order_by(OutboundRouteTrunk.position)
        )
    )
    return OutboundRouteRead(
        id=route.id,
        tenant_id=route.tenant_id,
        name=route.name,
        pattern=route.pattern,
        strip_digits=route.strip_digits,
        prepend=route.prepend,
        caller_id_number=route.caller_id_number,
        priority=route.priority,
        enabled=route.enabled,
        trunk_ids=trunk_ids,
        created_at=route.created_at,
        config_applied=applied,
    )


async def _owned_route(session: SessionDep, admin: User, route_id: uuid.UUID) -> OutboundRoute:
    route = await session.get(OutboundRoute, route_id)
    if route is None or (admin.role == Role.TENANT_ADMIN and route.tenant_id != admin.tenant_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Route not found")
    return route


def _set_trunks(session: SessionDep, route: OutboundRoute, trunk_ids: list[uuid.UUID]) -> None:
    for position, trunk_id in enumerate(trunk_ids):
        session.add(
            OutboundRouteTrunk(
                tenant_id=route.tenant_id, route_id=route.id, trunk_id=trunk_id, position=position
            )
        )


@outbound.get("")
async def list_outbound_routes(
    admin: TelephonyAdmin, session: SessionDep, tenant_id: uuid.UUID | None = None
) -> list[OutboundRouteRead]:
    stmt = select(OutboundRoute).order_by(OutboundRoute.priority, OutboundRoute.name)
    if admin.role == Role.TENANT_ADMIN:
        stmt = stmt.where(OutboundRoute.tenant_id == admin.tenant_id)
    elif tenant_id is not None:
        stmt = stmt.where(OutboundRoute.tenant_id == tenant_id)
    return [await _route_read(session, r) for r in (await session.scalars(stmt)).all()]


@outbound.post("", status_code=status.HTTP_201_CREATED)
async def create_outbound_route(
    body: OutboundRouteCreate,
    admin: TelephonyAdmin,
    session: SessionDep,
    settings: SettingsDep,
    ari: AriDep,
    kamailio: KamailioDep,
) -> OutboundRouteRead:
    tenant_id = await _tenant(session, admin, body.tenant_id)
    await _check_trunks(session, tenant_id, body.trunk_ids)
    route = OutboundRoute(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        **body.model_dump(exclude={"tenant_id", "trunk_ids"}),
    )
    session.add(route)
    await session.flush()
    _set_trunks(session, route, body.trunk_ids)
    await _commit(session, "A route with this name")
    await session.refresh(route)
    result = await apply_config(session, settings, ari, kamailio)
    return await _route_read(session, route, result.ok)


@outbound.patch("/{route_id}")
async def update_outbound_route(
    route_id: uuid.UUID,
    body: OutboundRouteUpdate,
    admin: TelephonyAdmin,
    session: SessionDep,
    settings: SettingsDep,
    ari: AriDep,
    kamailio: KamailioDep,
) -> OutboundRouteRead:
    route = await _owned_route(session, admin, route_id)
    changes = body.model_dump(exclude_unset=True)
    trunk_ids = changes.pop("trunk_ids", None)
    for key, value in changes.items():
        if value is None and key != "caller_id_number":
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"{key} cannot be null"
            )
        setattr(route, key, value)
    if trunk_ids is not None:
        await _check_trunks(session, route.tenant_id, trunk_ids)
        await session.execute(
            delete(OutboundRouteTrunk).where(OutboundRouteTrunk.route_id == route.id)
        )
        await session.flush()
        _set_trunks(session, route, trunk_ids)
    await _commit(session, "A route with this name")
    await session.refresh(route)
    result = await apply_config(session, settings, ari, kamailio)
    return await _route_read(session, route, result.ok)


@outbound.delete("/{route_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_outbound_route(
    route_id: uuid.UUID,
    admin: TelephonyAdmin,
    session: SessionDep,
    settings: SettingsDep,
    ari: AriDep,
    kamailio: KamailioDep,
) -> Response:
    await session.delete(await _owned_route(session, admin, route_id))
    await session.commit()
    await apply_config(session, settings, ari, kamailio)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ----------------------------------------------------------------------------- inbound


async def _owned_inbound(session: SessionDep, admin: User, route_id: uuid.UUID) -> InboundRoute:
    route = await session.get(InboundRoute, route_id)
    if route is None or (admin.role == Role.TENANT_ADMIN and route.tenant_id != admin.tenant_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Route not found")
    return route


async def _check_destination(session: SessionDep, tenant_id: uuid.UUID, number: str) -> None:
    exists = await session.scalar(
        select(Extension.id).where(Extension.tenant_id == tenant_id, Extension.number == number)
    )
    if exists is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="No extension with this number"
        )


async def _check_flow(session: SessionDep, tenant_id: uuid.UUID, flow_id: uuid.UUID) -> None:
    flow = await session.get(IvrFlow, flow_id)
    if flow is None or flow.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Flow not found")
    if flow.published_version is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Publish the flow before routing calls to it",
        )


def _inbound_read(route: InboundRoute, applied: bool | None = None) -> InboundRouteRead:
    return InboundRouteRead.model_validate(route).model_copy(update={"config_applied": applied})


@inbound.get("")
async def list_inbound_routes(
    admin: TelephonyAdmin, session: SessionDep, tenant_id: uuid.UUID | None = None
) -> list[InboundRouteRead]:
    stmt = select(InboundRoute).order_by(InboundRoute.did)
    if admin.role == Role.TENANT_ADMIN:
        stmt = stmt.where(InboundRoute.tenant_id == admin.tenant_id)
    elif tenant_id is not None:
        stmt = stmt.where(InboundRoute.tenant_id == tenant_id)
    return [_inbound_read(r) for r in await session.scalars(stmt)]


@inbound.post("", status_code=status.HTTP_201_CREATED)
async def create_inbound_route(
    body: InboundRouteCreate,
    admin: TelephonyAdmin,
    session: SessionDep,
    settings: SettingsDep,
    ari: AriDep,
    kamailio: KamailioDep,
) -> InboundRouteRead:
    tenant_id = await _tenant(session, admin, body.tenant_id)
    if body.trunk_id is not None:
        await _check_trunks(session, tenant_id, [body.trunk_id])
    if body.destination_number is not None:  # the schema requires exactly one of the two
        await _check_destination(session, tenant_id, body.destination_number)
    if body.destination_flow_id is not None:
        await _check_flow(session, tenant_id, body.destination_flow_id)
    route = InboundRoute(tenant_id=tenant_id, **body.model_dump(exclude={"tenant_id"}))
    session.add(route)
    await _commit(session, "A route for this number")
    await session.refresh(route)
    result = await apply_config(session, settings, ari, kamailio)
    return _inbound_read(route, result.ok)


@inbound.patch("/{route_id}")
async def update_inbound_route(
    route_id: uuid.UUID,
    body: InboundRouteUpdate,
    admin: TelephonyAdmin,
    session: SessionDep,
    settings: SettingsDep,
    ari: AriDep,
    kamailio: KamailioDep,
) -> InboundRouteRead:
    route = await _owned_inbound(session, admin, route_id)
    changes = body.model_dump(exclude_unset=True)
    for key, value in changes.items():
        if value is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"{key} cannot be null"
            )
        setattr(route, key, value)
    # one destination replaces the other
    if "destination_number" in changes:
        route.destination_flow_id = None
        await _check_destination(session, route.tenant_id, changes["destination_number"])
    if "destination_flow_id" in changes:
        route.destination_number = None
        await _check_flow(session, route.tenant_id, changes["destination_flow_id"])
    await _commit(session, "A route for this number")
    await session.refresh(route)
    result = await apply_config(session, settings, ari, kamailio)
    return _inbound_read(route, result.ok)


@inbound.delete("/{route_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_inbound_route(
    route_id: uuid.UUID,
    admin: TelephonyAdmin,
    session: SessionDep,
    settings: SettingsDep,
    ari: AriDep,
    kamailio: KamailioDep,
) -> Response:
    await session.delete(await _owned_inbound(session, admin, route_id))
    await session.commit()
    await apply_config(session, settings, ari, kamailio)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
