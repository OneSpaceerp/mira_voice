"""Prompt library: the tenant's recorded messages in Arabic, English and French (task 1.4).

Upload: PUT /api/v1/prompts/{id}/audio/{language} with the WAV file as the request body
(PCM 16-bit mono, 8 or 16 kHz, up to 5 minutes). The file is re-written cleanly and stored
where Asterisk plays it from (prompts.py).
"""

import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import cast, delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.types import Text

from mira_core import prompts as files
from mira_core.deps import SessionDep, SettingsDep, require_roles, scope_tenant
from mira_core.models import IvrFlow, IvrFlowVersion, Locale, Prompt, PromptAudio, Role, User

router = APIRouter(prefix="/api/v1/prompts", tags=["flows"])
FlowAdmin = Annotated[User, Depends(require_roles(Role.PLATFORM_ADMIN, Role.TENANT_ADMIN))]


class PromptCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    tenant_id: uuid.UUID | None = None


class PromptUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)


class AudioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    language: Locale
    sample_rate: int
    duration_ms: int
    size_bytes: int
    sha256: str


class PromptRead(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    description: str
    audio: list[AudioRead]


async def _read(session: SessionDep, prompt: Prompt) -> PromptRead:
    audio = await session.scalars(
        select(PromptAudio).where(PromptAudio.prompt_id == prompt.id).order_by(PromptAudio.language)
    )
    return PromptRead(
        id=prompt.id,
        tenant_id=prompt.tenant_id,
        name=prompt.name,
        description=prompt.description,
        audio=[AudioRead.model_validate(a) for a in audio],
    )


async def _owned(session: SessionDep, admin: User, prompt_id: uuid.UUID) -> Prompt:
    prompt = await session.get(Prompt, prompt_id)
    if prompt is None or (admin.role == Role.TENANT_ADMIN and prompt.tenant_id != admin.tenant_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Prompt not found")
    return prompt


async def _commit(session: SessionDep) -> None:
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="A prompt with this name already exists"
        ) from None


@router.get("")
async def list_prompts(
    admin: FlowAdmin, session: SessionDep, tenant_id: uuid.UUID | None = None
) -> list[PromptRead]:
    tid = scope_tenant(admin, tenant_id)
    found = await session.scalars(
        select(Prompt).where(Prompt.tenant_id == tid).order_by(Prompt.name)
    )
    return [await _read(session, p) for p in found.all()]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_prompt(body: PromptCreate, admin: FlowAdmin, session: SessionDep) -> PromptRead:
    prompt = Prompt(
        tenant_id=scope_tenant(admin, body.tenant_id), name=body.name, description=body.description
    )
    session.add(prompt)
    await _commit(session)
    await session.refresh(prompt)
    return await _read(session, prompt)


@router.patch("/{prompt_id}")
async def update_prompt(
    prompt_id: uuid.UUID, body: PromptUpdate, admin: FlowAdmin, session: SessionDep
) -> PromptRead:
    prompt = await _owned(session, admin, prompt_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"{key} cannot be null"
            )
        setattr(prompt, key, value)
    await _commit(session)
    return await _read(session, prompt)


@router.put("/{prompt_id}/audio/{language}")
async def upload_audio(
    prompt_id: uuid.UUID,
    language: Locale,
    request: Request,
    admin: FlowAdmin,
    session: SessionDep,
    settings: SettingsDep,
) -> PromptRead:
    """The request body is the WAV file itself (Content-Type: audio/wav)."""
    prompt = await _owned(session, admin, prompt_id)
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > files.MAX_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail="The file is too large")
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > files.MAX_BYTES:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail="The file is too large")
    try:
        audio = files.clean_wav(bytes(raw))
    except files.BadAudio as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from None
    files.store(
        Path(settings.prompts_dir),
        prompt.tenant_id,
        language.value,
        prompt.id,
        audio,
        settings.asterisk_config_gid,
    )
    await session.execute(
        delete(PromptAudio).where(
            PromptAudio.prompt_id == prompt.id, PromptAudio.language == language
        )
    )
    session.add(
        PromptAudio(
            tenant_id=prompt.tenant_id,
            prompt_id=prompt.id,
            language=language,
            sample_rate=audio.sample_rate,
            duration_ms=audio.duration_ms,
            size_bytes=len(audio.data),
            sha256=audio.sha256,
        )
    )
    await session.commit()
    return await _read(session, prompt)


@router.get("/{prompt_id}/audio/{language}")
async def download_audio(
    prompt_id: uuid.UUID,
    language: Locale,
    admin: FlowAdmin,
    session: SessionDep,
    settings: SettingsDep,
) -> FileResponse:
    """For listening to a prompt in the builder."""
    prompt = await _owned(session, admin, prompt_id)
    audio = await session.scalar(
        select(PromptAudio).where(
            PromptAudio.prompt_id == prompt.id, PromptAudio.language == language
        )
    )
    if audio is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No recording in this language")
    path = files.audio_path(
        Path(settings.prompts_dir), prompt.tenant_id, language.value, prompt.id, audio.sample_rate
    )
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="The recording file is missing")
    return FileResponse(
        path, media_type="audio/wav", filename=f"{prompt.name}-{language.value}.wav"
    )


@router.delete("/{prompt_id}/audio/{language}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_audio(
    prompt_id: uuid.UUID,
    language: Locale,
    admin: FlowAdmin,
    session: SessionDep,
    settings: SettingsDep,
) -> Response:
    prompt = await _owned(session, admin, prompt_id)
    await session.execute(
        delete(PromptAudio).where(
            PromptAudio.prompt_id == prompt.id, PromptAudio.language == language
        )
    )
    await session.commit()
    files.remove(Path(settings.prompts_dir), prompt.tenant_id, prompt.id, language.value)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{prompt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prompt(
    prompt_id: uuid.UUID, admin: FlowAdmin, session: SessionDep, settings: SettingsDep
) -> Response:
    """Refused while a flow's published version plays it (callers would hear silence)."""
    prompt = await _owned(session, admin, prompt_id)
    in_use = await session.scalar(
        select(IvrFlow.name)
        .join(
            IvrFlowVersion,
            (IvrFlowVersion.flow_id == IvrFlow.id)
            & (IvrFlowVersion.version == IvrFlow.published_version),
        )
        .where(cast(IvrFlowVersion.definition, Text).contains(str(prompt.id)))
        .limit(1)
    )
    if in_use:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail=f"The published flow '{in_use}' uses this prompt"
        )
    await session.delete(prompt)
    await session.commit()
    files.remove(Path(settings.prompts_dir), prompt.tenant_id, prompt.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
