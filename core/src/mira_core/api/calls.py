"""Calls: history, live view and call control over ARI (task 1.3).

Who sees what: platform admins (any tenant, name it), tenant admins and supervisors (their
tenant), agents (only calls they placed or answered). Call control: hang up a live call, and
click-to-call (ring the user's own extension, then dial the number from it).
"""

import uuid
from datetime import datetime
from typing import Annotated

import httpx
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from mira_core.asterisk_config import tenant_context
from mira_core.call_tracker import linkedid
from mira_core.deps import AriDep, CurrentUser, LiveDep, SessionDep
from mira_core.models import Call, CallDirection, CallEvent, Extension, Role, User
from mira_core.schemas import CallDetail, CallEventRead, CallRead, ClickToCall, LiveCallRead

router = APIRouter(prefix="/api/v1/calls", tags=["calls"])

_STAFF = (Role.TENANT_ADMIN, Role.SUPERVISOR)


def _tenant_of(user: User, requested: uuid.UUID | None) -> uuid.UUID:
    if user.role == Role.PLATFORM_ADMIN:
        if requested is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, detail="tenant_id is required"
            )
        return requested
    if user.tenant_id is None or requested not in (None, user.tenant_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return user.tenant_id


def _may_see(user: User, call: Call) -> bool:
    if user.role == Role.PLATFORM_ADMIN:
        return True
    if call.tenant_id != user.tenant_id:
        return False
    return user.role in _STAFF or call.agent_user_id == user.id


async def _owned_call(session: SessionDep, user: User, call_id: uuid.UUID) -> Call:
    call = await session.get(Call, call_id)
    if call is None or not _may_see(user, call):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Call not found")
    return call


@router.get("")
async def list_calls(
    user: CurrentUser,
    session: SessionDep,
    tenant_id: uuid.UUID | None = None,
    before: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[CallRead]:
    """Newest first. Page with `before` = the last `started_at` you received."""
    tid = _tenant_of(user, tenant_id)
    stmt = select(Call).where(Call.tenant_id == tid)
    if user.role == Role.AGENT:
        stmt = stmt.where(Call.agent_user_id == user.id)
    if before is not None:
        stmt = stmt.where(Call.started_at < before)
    stmt = stmt.order_by(Call.started_at.desc()).limit(limit)
    return [CallRead.model_validate(c) for c in await session.scalars(stmt)]


@router.get("/live")
async def live_calls(
    user: CurrentUser, live: LiveDep, tenant_id: uuid.UUID | None = None
) -> list[LiveCallRead]:
    tid = _tenant_of(user, tenant_id)
    calls = await live.list_tenant(tid)
    if user.role == Role.AGENT:
        calls = [c for c in calls if c.agent_user_id == str(user.id)]
    return [
        LiveCallRead(
            call_id=uuid.UUID(c.call_id),
            tenant_id=uuid.UUID(c.tenant_id),
            direction=CallDirection(c.direction),
            state=c.state,
            caller_number=c.caller_number,
            called_number=c.called_number,
            started_at=datetime.fromisoformat(c.started_at),
            answered_at=datetime.fromisoformat(c.answered_at) if c.answered_at else None,
            trunk_id=uuid.UUID(c.trunk_id) if c.trunk_id else None,
            agent_user_id=uuid.UUID(c.agent_user_id) if c.agent_user_id else None,
        )
        for c in calls
    ]


@router.get("/{call_id}")
async def get_call(call_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> CallDetail:
    call = await _owned_call(session, user, call_id)
    events = await session.scalars(
        select(CallEvent)
        .where(CallEvent.call_id == call.id)
        .order_by(CallEvent.occurred_at, CallEvent.id)
    )
    return CallDetail(
        **CallRead.model_validate(call).model_dump(),
        events=[CallEventRead.model_validate(e) for e in events],
    )


@router.post("/{call_id}/hangup", status_code=status.HTTP_202_ACCEPTED)
async def hangup_call(
    call_id: uuid.UUID, user: CurrentUser, session: SessionDep, ari: AriDep
) -> dict[str, int]:
    """Hang up every channel of a live call. The end is recorded when Asterisk reports it."""
    call = await _owned_call(session, user, call_id)
    if call.ended_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="The call has already ended")
    try:
        channels = [c for c in await ari.channels() if linkedid(c) == call.asterisk_linkedid]
        hung_up = sum([await ari.hangup(c["id"]) for c in channels])
    except httpx.HTTPError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail="Asterisk is not reachable"
        ) from None
    if not hung_up:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="The call has already ended")
    return {"channels": hung_up}


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def click_to_call(
    body: ClickToCall, user: CurrentUser, session: SessionDep, ari: AriDep
) -> dict[str, str]:
    """Ring the extension first; when the user picks up, Asterisk dials `number` from it,
    through the tenant's own dialplan (extensions, outbound routes, caller ID rules)."""
    if user.tenant_id is None:  # platform admins have no extension of their own
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Only tenant users can place calls")
    stmt = select(Extension).where(Extension.tenant_id == user.tenant_id, Extension.enabled)
    if body.extension_id is not None:
        stmt = stmt.where(Extension.id == body.extension_id)
    if user.role not in (Role.TENANT_ADMIN,) or body.extension_id is None:
        stmt = stmt.where(Extension.user_id == user.id)  # one's own phone unless an admin names one
    ext = (await session.scalars(stmt.order_by(Extension.number).limit(1))).first()
    if ext is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No extension to call from")
    # What the user's phone shows while it rings: the number about to be dialled. After the
    # pick-up the call carries the extension's own number as caller ID.
    caller_id = f'"Call {body.number}" <{ext.number}>'
    try:
        channel = await ari.originate(
            f"PJSIP/{ext.sip_username}", tenant_context(ext.tenant_id), body.number, caller_id
        )
    except httpx.HTTPError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail="Asterisk is not reachable"
        ) from None
    return {"channel_id": str(channel.get("id", "")), "extension": ext.number}
