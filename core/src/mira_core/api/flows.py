"""Mira Flow: IVR flows, their drafts and published versions (task 1.4, ADR 0009).

Editing: PUT saves the draft. It must be valid Mira Flow JSON node by node; wiring problems
(dangling links, unset variables, unreachable nodes) are reported but do not block saving.
Publishing: every check must pass (also prompts, mailboxes, queues of the tenant); the draft
becomes version N+1 and answers calls from then on. Rollback points back at an older version.
"""

import json
import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, StringConstraints, ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from mira_core.asterisk_config import apply_config
from mira_core.deps import (
    AriDep,
    CurrentUser,
    KamailioDep,
    SessionDep,
    SettingsDep,
    require_roles,
    scope_tenant,
)
from mira_core.flows import validate
from mira_core.flows.schema import MAX_NODES, FlowDefinition
from mira_core.models import Extension, IvrFlow, IvrFlowVersion, Role, User

router = APIRouter(prefix="/api/v1/flows", tags=["flows"])
FlowAdmin = Annotated[User, Depends(require_roles(Role.PLATFORM_ADMIN, Role.TENANT_ADMIN))]


FlowNumber = Annotated[str, StringConstraints(pattern=r"^[0-9]{2,16}$")]


class FlowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    number: FlowNumber | None = None  # dial it inside the tenant to run the flow
    draft: dict[str, Any] = Field(default_factory=dict)
    tenant_id: uuid.UUID | None = None


class FlowUpdate(BaseModel):
    """`number: null` removes the flow's number."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    number: FlowNumber | None = None
    draft: dict[str, Any] | None = None


class Report(BaseModel):
    errors: list[str]
    warnings: list[str]


class FlowRead(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    description: str
    draft: dict[str, Any]
    published_version: int | None
    number: str | None
    updated_at: datetime
    config_applied: bool | None = None
    report: Report | None = None  # wiring check of the draft


class VersionRead(BaseModel):
    version: int
    published_at: datetime
    published_by: uuid.UUID | None
    current: bool


class VersionDetail(VersionRead):
    definition: dict[str, Any]


class Rollback(BaseModel):
    version: int = Field(gt=0)


def _parse(draft: dict[str, Any]) -> FlowDefinition:
    try:
        return FlowDefinition.model_validate(draft)
    except ValidationError as exc:
        details = [
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
            for e in exc.errors(include_url=False)
        ]
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=details) from None


def _read(
    flow: IvrFlow, report: validate.FlowReport | None = None, applied: bool | None = None
) -> FlowRead:
    return FlowRead(
        number=flow.number,
        config_applied=applied,
        id=flow.id,
        tenant_id=flow.tenant_id,
        name=flow.name,
        description=flow.description,
        draft=flow.draft,
        published_version=flow.published_version,
        updated_at=flow.updated_at,
        report=Report(errors=report.errors, warnings=report.warnings) if report else None,
    )


MAX_DRAFT_BYTES = 256 * 1024


def _problem(error: Any) -> str:
    """A Pydantic error as '<node>: <field>: <message>' (the builder selects that node)."""
    loc = [str(p) for p in error["loc"]]
    if len(loc) >= 2 and loc[0] == "nodes":
        # ("nodes", "<id>", "<type tag>", "<field>", ...)
        field = ".".join(loc[3:]) or "type"
        return f"{loc[1]}: {field}: {error['msg']}"
    return f"{'.'.join(loc) or 'flow'}: {error['msg']}"


def _structure(draft: dict[str, Any]) -> validate.FlowReport | None:
    """The draft's problems. A draft is work in progress: it is saved even when nodes are
    not complete yet (empty links, no prompt chosen); publishing needs it fully valid."""
    if not draft:
        return None
    try:
        return validate.structure(FlowDefinition.model_validate(draft))
    except ValidationError as exc:
        return validate.FlowReport(errors=[_problem(e) for e in exc.errors(include_url=False)])


def _check_draft(draft: dict[str, Any]) -> None:
    """Shape and size limits for what is stored (the draft is never run)."""
    nodes = draft.get("nodes", {})
    if draft and (not isinstance(nodes, dict) or len(nodes) > MAX_NODES):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"nodes: at most {MAX_NODES} nodes"
        )
    if len(json.dumps(draft)) > MAX_DRAFT_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail="The flow is too large")


async def _owned(session: SessionDep, admin: User, flow_id: uuid.UUID) -> IvrFlow:
    flow = await session.get(IvrFlow, flow_id)
    if flow is None or (admin.role == Role.TENANT_ADMIN and flow.tenant_id != admin.tenant_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Flow not found")
    return flow


async def _check_number(session: SessionDep, tenant_id: uuid.UUID, number: str | None) -> None:
    """A flow number must not shadow an extension (both live in the tenant's dialplan)."""
    if number is None:
        return
    taken = await session.scalar(
        select(Extension.id).where(Extension.tenant_id == tenant_id, Extension.number == number)
    )
    if taken:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="An extension already has this number")


async def _commit(session: SessionDep) -> None:
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="A flow with this name or number already exists"
        ) from None


@router.get("/schema")
async def flow_schema(_: CurrentUser) -> dict[str, Any]:
    """JSON Schema of Mira Flow v1 (the builder and external tools use it)."""
    return FlowDefinition.model_json_schema(by_alias=True)


@router.get("")
async def list_flows(
    admin: FlowAdmin, session: SessionDep, tenant_id: uuid.UUID | None = None
) -> list[FlowRead]:
    tid = scope_tenant(admin, tenant_id)
    return [
        _read(f)
        for f in await session.scalars(
            select(IvrFlow).where(IvrFlow.tenant_id == tid).order_by(IvrFlow.name)
        )
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_flow(body: FlowCreate, admin: FlowAdmin, session: SessionDep) -> FlowRead:
    _check_draft(body.draft)
    report = _structure(body.draft)
    tenant_id = scope_tenant(admin, body.tenant_id)
    await _check_number(session, tenant_id, body.number)
    flow = IvrFlow(
        tenant_id=tenant_id,
        name=body.name,
        description=body.description,
        draft=body.draft,
        number=body.number,
    )
    session.add(flow)
    await _commit(session)
    await session.refresh(flow)
    return _read(flow, report)


@router.get("/{flow_id}")
async def get_flow(flow_id: uuid.UUID, admin: FlowAdmin, session: SessionDep) -> FlowRead:
    flow = await _owned(session, admin, flow_id)
    return _read(flow, _structure(flow.draft))


@router.put("/{flow_id}")
async def update_flow(
    flow_id: uuid.UUID,
    body: FlowUpdate,
    admin: FlowAdmin,
    session: SessionDep,
    settings: SettingsDep,
    ari: AriDep,
    kamailio: KamailioDep,
) -> FlowRead:
    flow = await _owned(session, admin, flow_id)
    changes = body.model_dump(exclude_unset=True)
    for key, value in changes.items():
        if value is None and key != "number":
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"{key} cannot be null"
            )
    if "draft" in changes:
        _check_draft(changes["draft"])
    if "number" in changes:
        await _check_number(session, flow.tenant_id, changes["number"])
    renumbered = "number" in changes and changes["number"] != flow.number
    for key, value in changes.items():
        setattr(flow, key, value)
    await _commit(session)
    await session.refresh(flow)
    applied = None
    if renumbered and flow.published_version is not None:
        applied = (await apply_config(session, settings, ari, kamailio)).ok
    return _read(flow, _structure(flow.draft), applied)


@router.post("/{flow_id}/publish")
async def publish_flow(
    flow_id: uuid.UUID,
    admin: FlowAdmin,
    session: SessionDep,
    settings: SettingsDep,
    ari: AriDep,
    kamailio: KamailioDep,
) -> FlowRead:
    """Every check must pass; the draft becomes the next version and answers calls."""
    flow = await _owned(session, admin, flow_id)
    if not flow.draft:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="The draft is empty")
    definition = _parse(flow.draft)
    report = await validate.references(session, flow.tenant_id, definition)
    if not report.ok:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"errors": report.errors, "warnings": report.warnings},
        )
    latest = await session.scalar(
        select(func.max(IvrFlowVersion.version)).where(IvrFlowVersion.flow_id == flow.id)
    )
    version = (latest or 0) + 1
    session.add(
        IvrFlowVersion(
            tenant_id=flow.tenant_id,
            flow_id=flow.id,
            version=version,
            # stored normalised: what the engine will run, exactly
            definition=definition.model_dump(mode="json", by_alias=True),
            published_by=admin.id,
        )
    )
    flow.published_version = version
    await session.commit()
    await session.refresh(flow)
    # the first publish puts the flow's number and routes into the dialplan
    applied = (await apply_config(session, settings, ari, kamailio)).ok
    return _read(flow, report, applied)


@router.get("/{flow_id}/versions")
async def list_versions(
    flow_id: uuid.UUID, admin: FlowAdmin, session: SessionDep
) -> list[VersionRead]:
    flow = await _owned(session, admin, flow_id)
    found = await session.scalars(
        select(IvrFlowVersion)
        .where(IvrFlowVersion.flow_id == flow.id)
        .order_by(IvrFlowVersion.version.desc())
    )
    return [
        VersionRead(
            version=v.version,
            published_at=v.published_at,
            published_by=v.published_by,
            current=v.version == flow.published_version,
        )
        for v in found
    ]


async def _version(session: SessionDep, flow: IvrFlow, version: int) -> IvrFlowVersion:
    found = await session.scalar(
        select(IvrFlowVersion).where(
            IvrFlowVersion.flow_id == flow.id, IvrFlowVersion.version == version
        )
    )
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Version not found")
    return found


@router.get("/{flow_id}/versions/{version}")
async def get_version(
    flow_id: uuid.UUID, version: int, admin: FlowAdmin, session: SessionDep
) -> VersionDetail:
    flow = await _owned(session, admin, flow_id)
    v = await _version(session, flow, version)
    return VersionDetail(
        version=v.version,
        published_at=v.published_at,
        published_by=v.published_by,
        current=v.version == flow.published_version,
        definition=v.definition,
    )


@router.post("/{flow_id}/rollback")
async def rollback_flow(
    flow_id: uuid.UUID, body: Rollback, admin: FlowAdmin, session: SessionDep
) -> FlowRead:
    """Answer calls with an older version again (checked again: a prompt may be gone)."""
    flow = await _owned(session, admin, flow_id)
    v = await _version(session, flow, body.version)
    report = await validate.references(session, flow.tenant_id, _parse(v.definition))
    if not report.ok:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"errors": report.errors, "warnings": report.warnings},
        )
    flow.published_version = v.version
    await session.commit()
    await session.refresh(flow)
    return _read(flow, _structure(flow.draft))


@router.post("/{flow_id}/versions/{version}/edit")
async def restore_draft(
    flow_id: uuid.UUID, version: int, admin: FlowAdmin, session: SessionDep
) -> FlowRead:
    """Copy a published version into the draft, to change it."""
    flow = await _owned(session, admin, flow_id)
    flow.draft = (await _version(session, flow, version)).definition
    await session.commit()
    await session.refresh(flow)
    return _read(flow, _structure(flow.draft))


@router.delete("/{flow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_flow(
    flow_id: uuid.UUID,
    admin: FlowAdmin,
    session: SessionDep,
    settings: SettingsDep,
    ari: AriDep,
    kamailio: KamailioDep,
) -> Response:
    """Refused while an inbound route sends calls to the flow."""
    flow = await _owned(session, admin, flow_id)
    await session.delete(flow)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="An inbound route sends calls to this flow"
        ) from None
    await apply_config(session, settings, ari, kamailio)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
