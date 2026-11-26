"""Login (OAuth2 password flow -> JWT) and the current user."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from mira_core.deps import CurrentUser, SessionDep, SettingsDep
from mira_core.models import Tenant, TenantStatus, User
from mira_core.schemas import Token, UserRead
from mira_core.security import TokenClaims, create_access_token, verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_BAD_LOGIN = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Incorrect e-mail or password",
    headers={"WWW-Authenticate": "Bearer"},
)


@router.post("/token")
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: SessionDep,
    settings: SettingsDep,
) -> Token:
    """`username` is the e-mail address. Same answer (and timing) for unknown user, wrong
    password, disabled account or suspended tenant: nothing to learn by guessing."""
    user = await session.scalar(select(User).where(User.email == form.username.strip().lower()))
    if not verify_password(form.password, user.password_hash if user else None) or user is None:
        raise _BAD_LOGIN
    if not user.is_active:
        raise _BAD_LOGIN
    if user.tenant_id is not None:
        tenant = await session.get(Tenant, user.tenant_id)
        if tenant is None or tenant.status != TenantStatus.ACTIVE:
            raise _BAD_LOGIN
    user.last_login_at = datetime.now(UTC)
    await session.commit()
    token, expires_in = create_access_token(
        TokenClaims(user_id=user.id, tenant_id=user.tenant_id, role=user.role), settings
    )
    return Token(access_token=token, expires_in=expires_in)


@router.get("/me")
async def me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)
