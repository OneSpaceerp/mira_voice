"""The Mira Flow worker (`mira-core ivr`, service `core-ivr`), task 1.4 stage 2.

Asterisk sends calls here with Stasis(mira-ivr,<flow id hex>) — from an inbound route or a
flow's own number (generated dialplan). The worker loads the flow's published version and
the tenant's prompts, runs it (FlowRun), and routes the channel's events to the run.
"""

import asyncio
import base64
import contextlib
import json
import logging
import signal
import uuid
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from mira_core.asterisk_config import IVR_APP, tenant_context
from mira_core.call_tracker import linkedid
from mira_core.config import Settings
from mira_core.db import get_sessionmaker
from mira_core.flows.ari import IvrAri
from mira_core.flows.engine import FlowContext, FlowRun
from mira_core.flows.http_dip import DataDip
from mira_core.flows.schema import FlowDefinition, prompt_ids
from mira_core.models import (
    Call,
    CallEvent,
    IvrFlow,
    IvrFlowVersion,
    PromptAudio,
    Queue,
    Tenant,
    Voicemail,
)

log = logging.getLogger(__name__)
HEARTBEAT_PATH = "/tmp/mira-ari-connected"  # noqa: S108 — container-local health marker


def _channel_of(event: dict[str, Any]) -> str:
    """Which channel an event is about (playbacks and recordings name it as target_uri)."""
    if event.get("channel"):
        return str(event["channel"].get("id", ""))
    for key in ("playback", "recording"):
        target = str((event.get(key) or {}).get("target_uri", ""))
        if target.startswith("channel:"):
            return target[len("channel:") :]
    return ""


class FlowWorker:
    def __init__(self, settings: Settings, ari: IvrAri, dip: DataDip) -> None:
        self.settings = settings
        self.ari = ari
        self.dip = dip
        self.sessions = get_sessionmaker()
        self.runs: dict[str, FlowRun] = {}
        self.tasks: set[asyncio.Task[None]] = set()

    def dispatch(self, event: dict[str, Any]) -> None:
        if event.get("type") == "StasisStart":
            channel = event.get("channel") or {}
            task = asyncio.create_task(
                self._start(channel, [str(a) for a in event.get("args") or []])
            )
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
            return
        run = self.runs.get(_channel_of(event))
        if run is not None:
            run.deliver(event)

    async def _start(self, channel: dict[str, Any], args: list[str]) -> None:
        cid = str(channel.get("id", ""))
        try:
            loaded = await self._load(channel, args)
        except Exception:
            log.exception("cannot load the flow for channel %s", cid)
            loaded = None
        if loaded is None:
            with contextlib.suppress(Exception):
                await self.ari.hangup(cid)
            return
        flow, ctx = loaded
        call_id = await self._call_id(channel)
        run = FlowRun(
            self.ari,
            channel,
            flow,
            ctx,
            dip=self.dip,
            journal=lambda kind, data: self._journal(channel, ctx, kind, data),
            save_voicemail=lambda box, name, secs: self._save_voicemail(
                channel, ctx, box, name, secs
            ),
            call_id=str(call_id or ""),
        )
        self.runs[cid] = run
        try:
            outcome = await run.run()
            log.info("flow %s v%d on %s: %s", ctx.flow_id, ctx.version, cid, outcome.kind)
        finally:
            self.runs.pop(cid, None)

    async def _load(
        self, channel: dict[str, Any], args: list[str]
    ) -> tuple[FlowDefinition, FlowContext] | None:
        try:
            flow_id = uuid.UUID(hex=args[0])
        except (IndexError, ValueError):
            log.warning("Stasis(%s) without a valid flow id: %s", IVR_APP, args)
            return None
        async with self.sessions() as session:
            flow = await session.get(IvrFlow, flow_id)
            if flow is None or flow.published_version is None:
                log.warning("flow %s is missing or not published", flow_id)
                return None
            # defence in depth: the channel's tenant must own the flow
            if str(channel.get("tenantid") or "") != str(flow.tenant_id):
                log.warning(
                    "channel of tenant %s asked for flow %s of another tenant",
                    channel.get("tenantid"),
                    flow_id,
                )
                return None
            version = await session.scalar(
                select(IvrFlowVersion).where(
                    IvrFlowVersion.flow_id == flow.id,
                    IvrFlowVersion.version == flow.published_version,
                )
            )
            tenant = await session.get(Tenant, flow.tenant_id)
            if version is None or tenant is None:
                return None
            definition = FlowDefinition.model_validate(version.definition)
            wanted = {p for n in definition.nodes.values() for p in prompt_ids(n)}
            prompts: dict[uuid.UUID, set[str]] = {}
            for audio in await session.scalars(
                select(PromptAudio).where(PromptAudio.prompt_id.in_(wanted))
            ):
                prompts.setdefault(audio.prompt_id, set()).add(audio.language.value)
            queues = {
                q.id: q.number
                for q in await session.scalars(
                    select(Queue).where(Queue.tenant_id == flow.tenant_id)
                )
                if q.number
            }
        ctx = FlowContext(
            tenant_id=flow.tenant_id,
            flow_id=flow.id,
            version=version.version,
            dialplan_context=tenant_context(flow.tenant_id),
            timezone=tenant.timezone,
            default_language=tenant.default_locale.value,
            prompts=prompts,
            queue_numbers=queues,
        )
        return definition, ctx

    async def _call_id(self, channel: dict[str, Any]) -> uuid.UUID | None:
        """The call record (written by core-events, usually a moment before Stasis starts)."""
        for _ in range(10):
            async with self.sessions() as session:
                found: uuid.UUID | None = await session.scalar(
                    select(Call.id).where(Call.asterisk_linkedid == linkedid(channel))
                )
            if found:
                return found
            await asyncio.sleep(0.2)
        return None

    async def _journal(
        self, channel: dict[str, Any], ctx: FlowContext, kind: str, data: dict[str, Any]
    ) -> None:
        """The IVR path, in call_events (node ids and outcomes only, never what was typed)."""
        call_id = await self._call_id(channel)
        if call_id is None:
            return
        async with self.sessions() as session:
            session.add(CallEvent(tenant_id=ctx.tenant_id, call_id=call_id, type=kind, data=data))
            await session.commit()

    async def _save_voicemail(
        self, channel: dict[str, Any], ctx: FlowContext, mailbox: str, name: str, seconds: int
    ) -> None:
        call_id = await self._call_id(channel)
        async with self.sessions() as session:
            session.add(
                Voicemail(
                    tenant_id=ctx.tenant_id,
                    mailbox=mailbox,
                    caller_number=str((channel.get("caller") or {}).get("number") or "")[:64],
                    call_id=call_id,
                    flow_id=ctx.flow_id,
                    recording_name=name,
                    duration_seconds=seconds,
                )
            )
            await session.commit()
        log.info("voicemail for %s: %ds", mailbox, seconds)


async def _heartbeat(every: float = 10.0) -> None:
    from pathlib import Path

    marker = Path(HEARTBEAT_PATH)
    while True:
        marker.touch()
        await asyncio.sleep(every)


async def run(settings: Settings, stop: asyncio.Event | None = None) -> None:
    stop = stop or asyncio.Event()
    ari = IvrAri(settings)
    worker = FlowWorker(settings, ari, DataDip(allow_private=settings.flow_http_allow_private))
    url = f"{settings.ari_events_url}?{urlencode({'app': IVR_APP})}"
    token = base64.b64encode(
        f"{settings.ari_user}:{settings.ari_password.get_secret_value()}".encode()
    ).decode()
    try:
        async for ws in connect(
            url, additional_headers={"Authorization": f"Basic {token}"}, ping_interval=20
        ):
            try:
                log.info("Mira Flow engine listening (app %s)", IVR_APP)
                beat = asyncio.create_task(_heartbeat())
                stopper = asyncio.create_task(stop.wait())

                async def consume(conn: Any = ws) -> None:
                    async for message in conn:
                        try:
                            worker.dispatch(json.loads(message))
                        except ValueError:
                            log.warning("ARI sent a non-JSON message")

                consumer = asyncio.create_task(consume())
                done, pending = await asyncio.wait(
                    {consumer, stopper}, return_when=asyncio.FIRST_COMPLETED
                )
                for task in (*pending, beat):
                    task.cancel()
                if stopper in done:
                    return
                consumer.result()
            except (ConnectionClosed, httpx.HTTPError) as exc:
                log.warning("ARI connection lost (%s); reconnecting", exc)
                continue
    finally:
        await ari.aclose()


def main(settings: Settings) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    async def _main() -> None:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)
        await run(settings, stop)

    asyncio.run(_main())
    return 0
