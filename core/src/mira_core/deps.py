"""Shared FastAPI dependencies: database session, current user, role checks."""

import uuid
from collections.abc import Callable, Coroutine
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from mira_core.asterisk_config import AsteriskAri, KamailioRpc
from mira_core.config import Settings, get_settings
from mira_core.db import get_session
from mira_core.live import LiveStore
from mira_core.models import Role, Tenant, TenantStatus, User
from mira_core.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)], session: SessionDep, settings: SettingsDep
) -> User:
    try:
        claims = decode_access_token(token, settings)
    except (jwt.InvalidTokenError, ValueError, KeyError):
        raise _UNAUTHORIZED from None
    user = await session.get(User, claims.user_id)
    # A token is only as good as the account behind it: a disabled user, a role change or a
    # suspended tenant takes effect on the next request, not when the token expires.
    if (
        user is None
        or not user.is_active
        or user.role != claims.role
        or user.tenant_id != claims.tenant_id
    ):
        raise _UNAUTHORIZED
    if user.tenant_id is not None:
        tenant = await session.get(Tenant, user.tenant_id)
        if tenant is None or tenant.status != TenantStatus.ACTIVE:
            raise _UNAUTHORIZED
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_ari(settings: SettingsDep) -> AsteriskAri:
    return AsteriskAri(settings)


AriDep = Annotated[AsteriskAri, Depends(get_ari)]


def get_kamailio(settings: SettingsDep) -> KamailioRpc:
    return KamailioRpc(settings)


KamailioDep = Annotated[KamailioRpc, Depends(get_kamailio)]


def get_live(request: Request) -> LiveStore:
    """Live call state (Valkey); the client is created once at startup (main.lifespan)."""
    return LiveStore(request.app.state.redis)


LiveDep = Annotated[LiveStore, Depends(get_live)]


def scope_tenant(admin: User, requested: uuid.UUID | None) -> uuid.UUID:
    """The tenant an admin acts on: always their own for a tenant admin (another tenant's id
    is "not found", never "forbidden", so ids cannot be probed); required for platform admins."""
    if admin.role == Role.TENANT_ADMIN:
        if admin.tenant_id is None:  # impossible by the users table constraint
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No tenant")
        if requested not in (None, admin.tenant_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Tenant not found")
        return admin.tenant_id
    if requested is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="tenant_id is required")
    return requested


def require_roles(*roles: Role) -> Callable[[User], Coroutine[Any, Any, User]]:
    """Dependency factory: 403 unless the current user has one of `roles`."""

    async def checker(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed for your role"
            )
        return user

    return checker
