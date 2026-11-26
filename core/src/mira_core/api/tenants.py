"""Tenants: created and listed by platform admins; a tenant's own admin can read it."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from mira_core.deps import CurrentUser, SessionDep, require_roles
from mira_core.models import Role, Tenant, User
from mira_core.schemas import TenantCreate, TenantRead

router = APIRouter(prefix="/api/v1/tenants", tags=["tenants"])

PlatformAdmin = Annotated[User, Depends(require_roles(Role.PLATFORM_ADMIN))]


@router.get("")
async def list_tenants(
    _: PlatformAdmin,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TenantRead]:
    rows = await session.scalars(select(Tenant).order_by(Tenant.name).limit(limit).offset(offset))
    return [TenantRead.model_validate(t) for t in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_tenant(body: TenantCreate, _: PlatformAdmin, session: SessionDep) -> TenantRead:
    tenant = Tenant(**body.model_dump())
    session.add(tenant)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="A tenant with this slug already exists"
        ) from None
    await session.refresh(tenant)
    return TenantRead.model_validate(tenant)


@router.get("/{tenant_id}")
async def get_tenant(tenant_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> TenantRead:
    # Anyone but a platform admin only ever sees their own tenant; others look like "not found".
    if user.role != Role.PLATFORM_ADMIN and user.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return TenantRead.model_validate(tenant)
