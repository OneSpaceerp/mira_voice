"""Extensions (SIP accounts for desk phones, Mira Desk and Mira Phone).

Creating or deleting one changes the database, which Asterisk reads live (realtime views),
and regenerates the telephony config (dialplan). The SIP password is generated here, shown once, never stored:
only its digest hash (HA1) is kept.
"""

import hashlib
import secrets
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
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
from mira_core.models import Extension, Role, Tenant, User
from mira_core.schemas import ExtensionCreate, ExtensionCredentials, ExtensionRead

router = APIRouter(prefix="/api/v1/extensions", tags=["extensions"])

ExtensionAdmin = Annotated[User, Depends(require_roles(Role.PLATFORM_ADMIN, Role.TENANT_ADMIN))]
SIP_REALM = "mira"


def sip_ha1(username: str, realm: str, password: str) -> str:
    # SIP digest (RFC 3261/7616) defines HA1 = MD5(user:realm:password); every SIP phone and
    # WebRTC stack supports MD5. Stored instead of the password; Asterisk gets "MD5:<ha1>".
    return hashlib.md5(f"{username}:{realm}:{password}".encode()).hexdigest()  # noqa: S324


def new_sip_password() -> str:
    return secrets.token_urlsafe(18)  # 144 bits


async def _get_owned(session: SessionDep, admin: User, extension_id: uuid.UUID) -> Extension:
    ext = await session.get(Extension, extension_id)
    if ext is None or (admin.role == Role.TENANT_ADMIN and ext.tenant_id != admin.tenant_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Extension not found")
    return ext


@router.get("")
async def list_extensions(
    admin: ExtensionAdmin, session: SessionDep, tenant_id: uuid.UUID | None = None
) -> list[ExtensionRead]:
    stmt = select(Extension).order_by(Extension.number)
    if admin.role == Role.TENANT_ADMIN:
        stmt = stmt.where(Extension.tenant_id == admin.tenant_id)
    elif tenant_id is not None:
        stmt = stmt.where(Extension.tenant_id == tenant_id)
    return [ExtensionRead.model_validate(e) for e in await session.scalars(stmt)]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_extension(
    body: ExtensionCreate,
    admin: ExtensionAdmin,
    session: SessionDep,
    settings: SettingsDep,
    ari: AriDep,
    kamailio: KamailioDep,
) -> ExtensionCredentials:
    tenant_id = scope_tenant(admin, body.tenant_id)
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    if body.user_id is not None:
        owner = await session.get(User, body.user_id)
        if owner is None or owner.tenant_id != tenant_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")

    # Globally unique SIP user (all tenants share the SIP edge): <slug>-<number>, max 64 chars.
    username = f"{tenant.slug[:47]}-{body.number}"
    password = new_sip_password()
    ext = Extension(
        tenant_id=tenant_id,
        number=body.number,
        user_id=body.user_id,
        display_name=body.display_name,
        sip_username=username,
        sip_ha1=sip_ha1(username, SIP_REALM, password),
        sip_realm=SIP_REALM,
        webrtc=body.webrtc,
    )
    session.add(ext)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="This extension number already exists"
        ) from None
    await session.refresh(ext)
    result = await apply_config(session, settings, ari, kamailio)
    return ExtensionCredentials(
        **ExtensionRead.model_validate(ext).model_dump(),
        sip_password=password,
        config_applied=result.ok,
    )


@router.post("/{extension_id}/password")
async def rotate_password(
    extension_id: uuid.UUID, admin: ExtensionAdmin, session: SessionDep
) -> ExtensionCredentials:
    """New SIP password; the old one stops working at the phone's next registration."""
    ext = await _get_owned(session, admin, extension_id)
    password = new_sip_password()
    ext.sip_ha1 = sip_ha1(ext.sip_username, ext.sip_realm, password)
    await session.commit()
    await session.refresh(ext)
    return ExtensionCredentials(
        **ExtensionRead.model_validate(ext).model_dump(), sip_password=password
    )


@router.delete("/{extension_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_extension(
    extension_id: uuid.UUID,
    admin: ExtensionAdmin,
    session: SessionDep,
    settings: SettingsDep,
    ari: AriDep,
    kamailio: KamailioDep,
) -> Response:
    ext = await _get_owned(session, admin, extension_id)
    await session.delete(ext)
    await session.commit()
    await apply_config(session, settings, ari, kamailio)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
