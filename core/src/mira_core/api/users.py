"""Users. Platform admins manage everyone; tenant admins manage their own tenant only."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from mira_core.deps import SessionDep, require_roles
from mira_core.models import Role, Tenant, User
from mira_core.schemas import UserCreate, UserRead
from mira_core.security import hash_password

router = APIRouter(prefix="/api/v1/users", tags=["users"])

UserAdmin = Annotated[User, Depends(require_roles(Role.PLATFORM_ADMIN, Role.TENANT_ADMIN))]


@router.get("")
async def list_users(
    admin: UserAdmin,
    session: SessionDep,
    tenant_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[UserRead]:
    stmt = select(User).order_by(User.email).limit(limit).offset(offset)
    if admin.role == Role.TENANT_ADMIN:
        stmt = stmt.where(User.tenant_id == admin.tenant_id)  # never anything else
    elif tenant_id is not None:
        stmt = stmt.where(User.tenant_id == tenant_id)
    rows = await session.scalars(stmt)
    return [UserRead.model_validate(u) for u in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_user(body: UserCreate, admin: UserAdmin, session: SessionDep) -> UserRead:
    if admin.role == Role.TENANT_ADMIN:
        if body.role == Role.PLATFORM_ADMIN:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, detail="Tenant admins cannot create platform admins"
            )
        if body.tenant_id not in (None, admin.tenant_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Tenant not found")
        tenant_id = admin.tenant_id
    elif body.role == Role.PLATFORM_ADMIN:
        if body.tenant_id is not None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Platform admins have no tenant"
            )
        tenant_id = None
    else:
        if body.tenant_id is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, detail="tenant_id is required for this role"
            )
        if await session.get(Tenant, body.tenant_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Tenant not found")
        tenant_id = body.tenant_id

    user = User(
        tenant_id=tenant_id,
        email=body.email,
        full_name=body.full_name,
        password_hash=hash_password(body.password),
        role=body.role,
        locale=body.locale,
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="A user with this e-mail already exists"
        ) from None
    await session.refresh(user)
    return UserRead.model_validate(user)
