"""Voicemail left through Mira Flow voicemail nodes (task 1.4 stage 2).

Agents see the messages of their own extensions' mailboxes; supervisors and tenant admins
see the tenant's. The audio stays in Asterisk's recording store and is fetched over ARI.
"""

import uuid
from datetime import datetime
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from mira_core.deps import CurrentUser, SessionDep, SettingsDep
from mira_core.flows.ari import IvrAri
from mira_core.models import Extension, Role, User, Voicemail

router = APIRouter(prefix="/api/v1/voicemails", tags=["flows"])


def get_ivr_ari(settings: SettingsDep) -> IvrAri:
    return IvrAri(settings)


IvrAriDep = Annotated[IvrAri, Depends(get_ivr_ari)]


class VoicemailRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    mailbox: str
    caller_number: str
    call_id: uuid.UUID | None
    duration_seconds: int
    heard: bool
    created_at: datetime


async def _mailboxes(session: SessionDep, user: User) -> set[str] | None:
    """None = every mailbox of the tenant."""
    if user.role in (Role.TENANT_ADMIN, Role.SUPERVISOR, Role.PLATFORM_ADMIN):
        return None
    return set(
        await session.scalars(
            select(Extension.number).where(
                Extension.tenant_id == user.tenant_id, Extension.user_id == user.id
            )
        )
    )


async def _owned(session: SessionDep, user: User, vm_id: uuid.UUID) -> Voicemail:
    vm = await session.get(Voicemail, vm_id)
    if vm is None or (user.role != Role.PLATFORM_ADMIN and vm.tenant_id != user.tenant_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Message not found")
    boxes = await _mailboxes(session, user)
    if boxes is not None and vm.mailbox not in boxes:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Message not found")
    return vm


@router.get("")
async def list_voicemails(
    user: CurrentUser,
    session: SessionDep,
    tenant_id: uuid.UUID | None = None,
    mailbox: str | None = None,
) -> list[VoicemailRead]:
    if user.role == Role.PLATFORM_ADMIN:
        if tenant_id is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, detail="tenant_id is required"
            )
        tid = tenant_id
    else:
        if user.tenant_id is None or tenant_id not in (None, user.tenant_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Tenant not found")
        tid = user.tenant_id
    stmt = select(Voicemail).where(Voicemail.tenant_id == tid)
    boxes = await _mailboxes(session, user)
    if boxes is not None:
        stmt = stmt.where(Voicemail.mailbox.in_(boxes))
    if mailbox is not None:
        stmt = stmt.where(Voicemail.mailbox == mailbox)
    stmt = stmt.order_by(Voicemail.created_at.desc()).limit(200)
    return [VoicemailRead.model_validate(v) for v in await session.scalars(stmt)]


@router.get("/{vm_id}/audio")
async def voicemail_audio(
    vm_id: uuid.UUID, user: CurrentUser, session: SessionDep, ari: IvrAriDep
) -> Response:
    """The message as WAV. Listening marks it heard."""
    vm = await _owned(session, user, vm_id)
    try:
        data = await ari.recording_file(vm.recording_name)
    except httpx.HTTPError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail="Asterisk is not reachable"
        ) from None
    finally:
        await ari.aclose()
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="The recording is gone")
    vm.heard = True
    await session.commit()
    return Response(content=data, media_type="audio/wav")


@router.delete("/{vm_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_voicemail(
    vm_id: uuid.UUID, user: CurrentUser, session: SessionDep, ari: IvrAriDep
) -> Response:
    vm = await _owned(session, user, vm_id)
    try:
        await ari.delete_recording(vm.recording_name)
    except httpx.HTTPError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail="Asterisk is not reachable"
        ) from None
    finally:
        await ari.aclose()
    await session.delete(vm)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
