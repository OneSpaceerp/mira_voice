"""The ARI event worker (`mira-core call-events`, service `core-events`), task 1.3.

Connects to Asterisk's event WebSocket as the Stasis application `mira` with subscribeAll
(events for every channel, without moving the dialplan into ARI), narrows the stream with an
event filter, re-reads the active channels after every (re)connect, and hands each event to
the CallTracker. One worker per Asterisk node; it is the only writer of live state.
"""

import asyncio
import base64
import json
import logging
import signal
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
from redis.asyncio import Redis
from redis.exceptions import RedisError
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from mira_core.call_tracker import EVENT_TYPES, CallTracker
from mira_core.config import Settings
from mira_core.db import get_sessionmaker
from mira_core.live import LiveStore

log = logging.getLogger(__name__)


def _auth(settings: Settings) -> tuple[str, str]:
    return settings.ari_user, settings.ari_password.get_secret_value()


async def set_event_filter(client: httpx.AsyncClient, app: str) -> None:
    """Only the event types the tracker uses (DTMF, variables etc. never leave Asterisk)."""
    body = {"allowed": [{"type": t} for t in EVENT_TYPES]}
    r = await client.put(f"/applications/{app}/eventFilter", json=body)
    r.raise_for_status()


async def active_channels(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    r = await client.get("/channels")
    r.raise_for_status()
    channels: list[dict[str, Any]] = r.json()
    return channels


async def consume(ws: ClientConnection, tracker: CallTracker) -> None:
    async for message in ws:
        try:
            event = json.loads(message)
        except ValueError:
            log.warning("ARI sent a non-JSON message")
            continue
        try:
            await tracker.handle(event)
        except Exception:  # one bad event must not stop call tracking
            log.exception("could not process %s", event.get("type"))


HEARTBEAT = Path("/tmp/mira-ari-connected")  # noqa: S108 — container-local health marker


async def heartbeat(
    tracker: CallTracker, redis: Redis, path: Path = HEARTBEAT, every: float = 10.0
) -> None:
    """While connected to ARI: touch the marker the container health check looks at, and
    notice a Valkey restart (new run_id: it came back empty) to publish the live calls again."""
    run_id: str | None = None
    while True:
        path.touch()
        try:
            current = str((await redis.info("server")).get("run_id", ""))
            if run_id is not None and current != run_id:
                log.warning("Valkey restarted: publishing %d live calls again", len(tracker.calls))
                await tracker.republish()
            run_id = current
        except RedisError as exc:
            log.warning("Valkey not reachable: %s", exc)
        await asyncio.sleep(every)


async def run(settings: Settings, stop: asyncio.Event | None = None) -> None:
    stop = stop or asyncio.Event()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    tracker = CallTracker(get_sessionmaker(), LiveStore(redis))
    query = urlencode({"app": settings.ari_app, "subscribeAll": "true"})
    url = f"{settings.ari_events_url}?{query}"
    user, password = _auth(settings)
    # credentials in a header, not in the URL (ARI also accepts ?api_key=, which ends up in logs)
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    headers = {"Authorization": f"Basic {token}"}
    async with httpx.AsyncClient(
        base_url=settings.ari_url, auth=(user, password), timeout=10.0
    ) as rest:
        try:
            # connect() as an iterator reconnects with exponential backoff (websockets docs)
            async for ws in connect(url, additional_headers=headers, ping_interval=20):
                try:
                    await set_event_filter(rest, settings.ari_app)
                    await tracker.reconcile(await active_channels(rest))
                    log.info("listening to ARI events (app %s)", settings.ari_app)
                    consumer = asyncio.create_task(consume(ws, tracker))
                    stopper = asyncio.create_task(stop.wait())
                    beat = asyncio.create_task(heartbeat(tracker, redis))
                    done, pending = await asyncio.wait(
                        {consumer, stopper}, return_when=asyncio.FIRST_COMPLETED
                    )
                    for task in (*pending, beat):
                        task.cancel()
                    if stopper in done:
                        return
                    consumer.result()  # re-raise ConnectionClosed etc.
                except (ConnectionClosed, httpx.HTTPError) as exc:
                    log.warning("ARI connection lost (%s); reconnecting", exc)
                    continue
        finally:
            await redis.aclose()


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
