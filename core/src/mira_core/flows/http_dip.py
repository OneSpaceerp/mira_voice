"""The data dip of a Mira Flow (`http` node): call a web service during the call.

Safety (ADR 0009/0010): the host is fixed in the flow; at call time every address it resolves
to is checked and the request goes to that checked address (Host header and TLS SNI keep the
name, so certificates are verified as usual) — DNS cannot swap in an internal address between
the check and the connection. Always blocked: loopback (every Mira service listens there),
link-local (cloud metadata), multicast, unspecified and reserved ranges. Private LAN ranges
are allowed on the Server edition (ERPNext usually lives there) unless
MIRA_FLOW_HTTP_ALLOW_PRIVATE=false (Mira Cloud). No redirects, 64 KB answers at most.
"""

import asyncio
import ipaddress
import json
import logging
import socket
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import httpx

from mira_core.flows.schema import PLACEHOLDER, HttpRequest

log = logging.getLogger(__name__)
MAX_ANSWER = 64 * 1024
Resolver = Callable[[str, int], Awaitable[list[str]]]


class Blocked(Exception):
    pass


async def system_resolver(host: str, port: int) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return sorted({str(info[4][0]) for info in infos})


def allowed(address: str, allow_private: bool) -> bool:
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved:
        return False
    if ip.is_private and not ip.is_global:
        return allow_private
    return True


def render(template: str, variables: dict[str, str], *, quote_values: bool = False) -> str:
    def value(match: Any) -> str:
        v = variables.get(match.group(1), "")
        v = v.replace("\r", "").replace("\n", "")
        return quote(v, safe="") if quote_values else v

    return PLACEHOLDER.sub(value, template)


def extract(data: Any, path: str) -> str:
    """'message.customer.0.name' -> the value, '' when the path is not there."""
    for part in path.split("."):
        if isinstance(data, dict) and part in data:
            data = data[part]
        elif isinstance(data, list) and part.isdigit() and int(part) < len(data):
            data = data[int(part)]
        else:
            return ""
    if isinstance(data, bool):
        return "1" if data else "0"
    if isinstance(data, dict | list):
        return json.dumps(data, ensure_ascii=False)[:500]
    return "" if data is None else str(data)[:500]


class DataDip:
    def __init__(
        self,
        allow_private: bool = True,
        resolver: Resolver = system_resolver,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.allow_private = allow_private
        self.resolver = resolver
        self.transport = transport

    async def call(self, node: HttpRequest, variables: dict[str, str]) -> dict[str, str] | None:
        """The extracted variables, or None when the service failed (-> error_next)."""
        try:
            return await asyncio.wait_for(
                self._call(node, variables), timeout=node.timeout_seconds + 1
            )
        except (Blocked, httpx.HTTPError, ValueError, TimeoutError, OSError) as exc:
            log.warning("data dip to %s failed: %s", urlsplit(node.url).hostname, exc)
            return None

    async def _call(self, node: HttpRequest, variables: dict[str, str]) -> dict[str, str]:
        url = urlsplit(render(node.url, variables, quote_values=True))
        host = url.hostname or ""
        port = url.port or (443 if url.scheme == "https" else 80)
        addresses = await self.resolver(host, port)
        if not addresses or not all(allowed(a, self.allow_private) for a in addresses):
            raise Blocked(f"{host} resolves to a blocked address")
        ip = addresses[0]
        netloc = f"[{ip}]" if ":" in ip else ip
        if url.port:
            netloc += f":{url.port}"
        target = urlunsplit((url.scheme, netloc, url.path or "/", url.query, ""))
        headers = {k: render(v, variables) for k, v in node.headers.items()}
        headers["Host"] = host if not url.port else f"{host}:{url.port}"
        headers.setdefault("Accept", "application/json")
        body = (
            {k: render(v, variables) for k, v in node.body.items()}
            if node.method == "POST"
            else None
        )
        async with (
            httpx.AsyncClient(
                timeout=node.timeout_seconds, follow_redirects=False, transport=self.transport
            ) as client,
            client.stream(
                node.method,
                target,
                headers=headers,
                json=body,
                extensions={"sni_hostname": host},
            ) as r,
        ):
            if r.status_code >= 300:
                raise httpx.HTTPError(f"status {r.status_code}")
            raw = bytearray()
            async for chunk in r.aiter_bytes():
                raw.extend(chunk)
                if len(raw) > MAX_ANSWER:
                    raise ValueError("answer larger than 64 KB")
        data = json.loads(raw.decode("utf-8")) if raw else {}
        return {var: extract(data, path) for var, path in node.extract.items()}
