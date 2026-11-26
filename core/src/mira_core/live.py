"""Live call state in Valkey (Redis protocol), task 1.3.

Only what is happening *now* lives here; PostgreSQL keeps the history. The event worker
(`mira-core call-events`) is the only writer and rebuilds everything from Asterisk at start,
so Valkey runs without persistence.

Keys (all prefixed `mira:`):
    mira:call:<call id>            hash  one active call (see LiveCall)
    mira:tenant:<tenant id>:calls  set   ids of the tenant's active calls
Channel:
    mira:tenant:<tenant id>:events pub/sub  {"type": "call.started" | "call.updated" |
                                             "call.ended", "call": {...}} — wallboards, Mira Desk
"""

import json
import uuid
from dataclasses import asdict, dataclass, fields
from typing import Any

from redis.asyncio import Redis

PREFIX = "mira:"
CALL_TTL_SECONDS = 12 * 3600  # safety net: a call never stays "live" longer than this


def call_key(call_id: uuid.UUID | str) -> str:
    return f"{PREFIX}call:{call_id}"


def tenant_calls_key(tenant_id: uuid.UUID | str) -> str:
    return f"{PREFIX}tenant:{tenant_id}:calls"


def tenant_events_channel(tenant_id: uuid.UUID | str) -> str:
    return f"{PREFIX}tenant:{tenant_id}:events"


@dataclass
class LiveCall:
    call_id: str
    tenant_id: str
    direction: str
    state: str  # "ringing" until a called party answers, then "up"
    caller_number: str
    called_number: str
    started_at: str  # ISO 8601, UTC
    answered_at: str = ""
    trunk_id: str = ""
    agent_user_id: str = ""

    def as_hash(self) -> dict[str, str]:
        return {k: str(v) for k, v in asdict(self).items()}

    @classmethod
    def from_hash(cls, data: dict[str, str]) -> "LiveCall":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in names})


class LiveStore:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def put(self, call: LiveCall, event: str) -> None:
        """Create or update an active call and tell the tenant's subscribers."""
        key = call_key(call.call_id)
        # typed with redis-py's own key/value union (its Mapping parameter is invariant)
        mapping: dict[bytes | bytearray | memoryview[int] | str | int | float, Any] = {
            k: v for k, v in call.as_hash().items()
        }
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.hset(key, mapping=mapping)
            pipe.expire(key, CALL_TTL_SECONDS)
            pipe.sadd(tenant_calls_key(call.tenant_id), call.call_id)
            pipe.publish(tenant_events_channel(call.tenant_id), _message(event, call))
            await pipe.execute()

    async def end(self, call: LiveCall) -> None:
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.delete(call_key(call.call_id))
            pipe.srem(tenant_calls_key(call.tenant_id), call.call_id)
            pipe.publish(tenant_events_channel(call.tenant_id), _message("call.ended", call))
            await pipe.execute()

    async def list_tenant(self, tenant_id: uuid.UUID | str) -> list[LiveCall]:
        # the client is created with decode_responses=True: keys and values come back as str
        ids = sorted(_text(i) for i in await self.redis.smembers(tenant_calls_key(tenant_id)))
        calls: list[LiveCall] = []
        for call_id in ids:
            data = await self.redis.hgetall(call_key(call_id))
            if data:
                calls.append(LiveCall.from_hash({_text(k): _text(v) for k, v in data.items()}))
            else:  # expired hash: tidy the set
                await self.redis.srem(tenant_calls_key(tenant_id), call_id)
        return calls

    async def clear(self) -> None:
        """Forget all live state (the worker rebuilds it from Asterisk at start)."""
        async for key in self.redis.scan_iter(match=f"{PREFIX}call:*"):
            await self.redis.delete(key)
        async for key in self.redis.scan_iter(match=f"{PREFIX}tenant:*:calls"):
            await self.redis.delete(key)


def _text(value: str | bytes) -> str:
    return value.decode() if isinstance(value, bytes) else value


def _message(event: str, call: LiveCall) -> str:
    body: dict[str, Any] = {"type": event, "call": asdict(call)}
    return json.dumps(body, separators=(",", ":"))
