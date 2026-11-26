"""Trunks: carrier connections (task 1.2, ADR 0007).

- sip_register (e.g. WE): Mira registers to the carrier with a username and password.
- sip_ip_auth: the carrier trusts our public IP; its calls come from `inbound_ips`.
- gsm_gateway (Yeastar / Dinstar): the box registers to Mira like a phone. Mira generates its
  SIP account; the password is shown once and only its digest hash is kept.

Carrier passwords are encrypted at rest (Fernet, MIRA_DATA_KEY) and never returned. Every change
regenerates the telephony config (Asterisk pjsip + dialplan, Kamailio carrier list).
"""

import contextlib
import ipaddress
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from mira_core import crypto
from mira_core.api.extensions import SIP_REALM, new_sip_password, sip_ha1
from mira_core.asterisk_config import apply_config
from mira_core.deps import (
    AriDep,
    KamailioDep,
    SessionDep,
    SettingsDep,
    require_roles,
    scope_tenant,
)
from mira_core.models import Role, Tenant, Trunk, TrunkKind, User
from mira_core.schemas import TrunkCreate, TrunkCredentials, TrunkRead, TrunkUpdate

router = APIRouter(prefix="/api/v1/trunks", tags=["trunks"])

TelephonyAdmin = Annotated[User, Depends(require_roles(Role.PLATFORM_ADMIN, Role.TENANT_ADMIN))]
GSM_HOST = "dynamic"  # a GSM gateway has no fixed address: it registers


def trunk_read(trunk: Trunk, config_applied: bool | None = None) -> TrunkRead:
    return TrunkRead(
        id=trunk.id,
        tenant_id=trunk.tenant_id,
        name=trunk.name,
        kind=trunk.kind,
        host=trunk.host,
        port=trunk.port,
        transport=trunk.transport,
        auth_username=trunk.auth_username,
        from_domain=trunk.from_domain,
        caller_id_number=trunk.caller_id_number,
        max_channels=trunk.max_channels,
        inbound_ips=list(trunk.inbound_ips or []),
        enabled=trunk.enabled,
        has_password=bool(trunk.auth_secret_enc or trunk.sip_ha1),
        sip_username=trunk.asterisk_id if trunk.kind is TrunkKind.GSM_GATEWAY else None,
        created_at=trunk.created_at,
        config_applied=config_applied,
    )


async def get_owned_trunk(session: SessionDep, admin: User, trunk_id: uuid.UUID) -> Trunk:
    trunk = await session.get(Trunk, trunk_id)
    if trunk is None or (admin.role == Role.TENANT_ADMIN and trunk.tenant_id != admin.tenant_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Trunk not found")
    return trunk


async def _commit(session: SessionDep) -> None:
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="A trunk with this name already exists"
        ) from None


def _source_ips(ips: list[str], host: str) -> set[str]:
    """Carrier signalling addresses: the listed IPs, plus the host when it is a literal IP."""
    found = set(ips)
    with contextlib.suppress(ValueError):
        found.add(str(ipaddress.ip_address(host)))
    return found


async def _carrier_ips_free(
    session: SessionDep, ips: list[str], host: str, trunk_id: uuid.UUID | None
) -> None:
    """A carrier IP identifies exactly one trunk (Kamailio tags its calls with that trunk)."""
    wanted = _source_ips(ips, host)
    if not wanted:
        return
    stmt = select(Trunk).where(Trunk.kind != TrunkKind.GSM_GATEWAY)
    if trunk_id is not None:
        stmt = stmt.where(Trunk.id != trunk_id)
    for other in await session.scalars(stmt):
        if wanted & _source_ips(list(other.inbound_ips or []), other.host):
            # Do not tell a tenant admin which other tenant uses it.
            raise HTTPException(
                status.HTTP_409_CONFLICT, detail="This carrier IP is already used by another trunk"
            )


@router.get("")
async def list_trunks(
    admin: TelephonyAdmin, session: SessionDep, tenant_id: uuid.UUID | None = None
) -> list[TrunkRead]:
    stmt = select(Trunk).order_by(Trunk.name)
    if admin.role == Role.TENANT_ADMIN:
        stmt = stmt.where(Trunk.tenant_id == admin.tenant_id)
    elif tenant_id is not None:
        stmt = stmt.where(Trunk.tenant_id == tenant_id)
    return [trunk_read(t) for t in await session.scalars(stmt)]


@router.get("/{trunk_id}")
async def get_trunk(trunk_id: uuid.UUID, admin: TelephonyAdmin, session: SessionDep) -> TrunkRead:
    return trunk_read(await get_owned_trunk(session, admin, trunk_id))


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_trunk(
    body: TrunkCreate,
    admin: TelephonyAdmin,
    session: SessionDep,
    settings: SettingsDep,
    ari: AriDep,
    kamailio: KamailioDep,
) -> TrunkRead | TrunkCredentials:
    tenant_id = scope_tenant(admin, body.tenant_id)
    if await session.get(Tenant, tenant_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    ips = [str(ip) for ip in body.inbound_ips]
    trunk = Trunk(
        id=uuid.uuid4(),  # needed now: a GSM gateway's SIP username is derived from it
        tenant_id=tenant_id,
        name=body.name,
        kind=body.kind,
        host=body.host or GSM_HOST,
        port=body.port,
        transport=body.transport,
        auth_username=body.auth_username,
        from_domain=body.from_domain,
        caller_id_number=body.caller_id_number,
        max_channels=body.max_channels,
        inbound_ips=ips if body.kind is not TrunkKind.GSM_GATEWAY else [],
        enabled=body.enabled,
    )
    gateway_password: str | None = None
    if body.kind is TrunkKind.GSM_GATEWAY:
        gateway_password = new_sip_password()
        trunk.sip_ha1 = sip_ha1(trunk.asterisk_id, SIP_REALM, gateway_password)
    else:
        await _carrier_ips_free(session, ips, trunk.host, None)
        if body.password is not None:
            trunk.auth_secret_enc = crypto.encrypt(body.password.get_secret_value())
    session.add(trunk)
    await _commit(session)
    await session.refresh(trunk)
    result = await apply_config(session, settings, ari, kamailio)
    read = trunk_read(trunk, result.ok)
    if gateway_password is not None:
        return TrunkCredentials(
            **read.model_dump(), sip_password=gateway_password, sip_realm=SIP_REALM
        )
    return read


@router.patch("/{trunk_id}")
async def update_trunk(
    trunk_id: uuid.UUID,
    body: TrunkUpdate,
    admin: TelephonyAdmin,
    session: SessionDep,
    settings: SettingsDep,
    ari: AriDep,
    kamailio: KamailioDep,
) -> TrunkRead:
    trunk = await get_owned_trunk(session, admin, trunk_id)
    changes = body.model_dump(exclude_unset=True)
    gsm = trunk.kind is TrunkKind.GSM_GATEWAY
    if gsm and {"host", "auth_username", "password", "inbound_ips"} & changes.keys():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A GSM gateway registers to Mira: use POST /password for a new account password",
        )
    if "password" in changes:
        secret = body.password
        trunk.auth_secret_enc = crypto.encrypt(secret.get_secret_value()) if secret else None
        del changes["password"]
    if "inbound_ips" in changes:
        changes["inbound_ips"] = [str(ip) for ip in body.inbound_ips or []]
    for key, value in changes.items():
        if value is None and key in (
            "name",
            "host",
            "port",
            "transport",
            "max_channels",
            "enabled",
        ):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"{key} cannot be null"
            )
        setattr(trunk, key, value)
    if trunk.kind is TrunkKind.SIP_REGISTER and not (trunk.auth_username and trunk.auth_secret_enc):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A registering trunk needs auth_username and password",
        )
    if not gsm:
        await _carrier_ips_free(session, list(trunk.inbound_ips or []), trunk.host, trunk.id)
    await _commit(session)
    await session.refresh(trunk)
    result = await apply_config(session, settings, ari, kamailio)
    return trunk_read(trunk, result.ok)


@router.post("/{trunk_id}/password")
async def rotate_gateway_password(
    trunk_id: uuid.UUID,
    admin: TelephonyAdmin,
    session: SessionDep,
    settings: SettingsDep,
    ari: AriDep,
    kamailio: KamailioDep,
) -> TrunkCredentials:
    """GSM gateway: new SIP password; the old one stops working at its next registration."""
    trunk = await get_owned_trunk(session, admin, trunk_id)
    if trunk.kind is not TrunkKind.GSM_GATEWAY:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Only GSM gateways have a Mira-generated password; PATCH the carrier password",
        )
    password = new_sip_password()
    trunk.sip_ha1 = sip_ha1(trunk.asterisk_id, SIP_REALM, password)
    await session.commit()
    await session.refresh(trunk)
    result = await apply_config(session, settings, ari, kamailio)
    return TrunkCredentials(
        **trunk_read(trunk, result.ok).model_dump(), sip_password=password, sip_realm=SIP_REALM
    )


@router.delete("/{trunk_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trunk(
    trunk_id: uuid.UUID,
    admin: TelephonyAdmin,
    session: SessionDep,
    settings: SettingsDep,
    ari: AriDep,
    kamailio: KamailioDep,
) -> Response:
    """Also removes the trunk from its outbound routes and its inbound routes (cascade)."""
    trunk = await get_owned_trunk(session, admin, trunk_id)
    await session.delete(trunk)
    await session.commit()
    await apply_config(session, settings, ari, kamailio)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
