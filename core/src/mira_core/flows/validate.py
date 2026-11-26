"""Checks a Mira Flow beyond its JSON shape (task 1.4).

structure(): links, reachability, variables — no database needed (used while editing).
references(): prompts, extensions, queues and timezones of the tenant (required to publish).
A flow can only be published with no errors; warnings are shown in the builder.
"""

import uuid
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mira_core.flows.schema import (
    BUILTIN_VARIABLES,
    Branch,
    Collect,
    FlowDefinition,
    HttpRequest,
    QueueNode,
    SetVariable,
    TimeCondition,
    Voicemail,
    next_ids,
    prompt_ids,
    template_variables,
)
from mira_core.models import Extension, Prompt, PromptAudio, Queue


@dataclass
class FlowReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _defined_variables(flow: FlowDefinition) -> set[str]:
    names = set(BUILTIN_VARIABLES)
    for node in flow.nodes.values():
        if isinstance(node, Collect | SetVariable):
            names.add(node.variable)
        if isinstance(node, HttpRequest):
            names.update(node.extract)
    return names


def _used_variables(node: BaseModel) -> set[str]:
    used: set[str] = set()
    if isinstance(node, SetVariable):
        used |= template_variables(node.value)
    if isinstance(node, Branch):
        used.add(node.variable)
        for c in node.conditions:
            used |= template_variables(c.value)
    if isinstance(node, HttpRequest):
        used |= template_variables(node.url)
        for value in [*node.headers.values(), *node.body.values()]:
            used |= template_variables(value)
    return used


def structure(flow: FlowDefinition) -> FlowReport:
    report = FlowReport()
    if flow.start not in flow.nodes:
        report.errors.append(f"start node '{flow.start}' does not exist")
        return report
    for node_id, node in flow.nodes.items():
        for target in next_ids(node):
            if target not in flow.nodes:
                report.errors.append(f"{node_id}: goes to '{target}', which does not exist")
            elif target == node_id and not isinstance(node, Branch):
                report.errors.append(f"{node_id}: goes to itself")
    defined = _defined_variables(flow)
    for node_id, node in flow.nodes.items():
        for var in sorted(_used_variables(node) - defined):
            report.errors.append(f"{node_id}: variable '{var}' is never set")
    # reachability from start (warnings: the builder may hold nodes still being wired)
    seen, todo = set(), [flow.start]
    while todo:
        current = todo.pop()
        if current in seen or current not in flow.nodes:
            continue
        seen.add(current)
        todo.extend(next_ids(flow.nodes[current]))
    for node_id in flow.nodes:
        if node_id not in seen:
            report.warnings.append(f"{node_id}: not reachable from the start")
    return report


async def references(
    session: AsyncSession, tenant_id: uuid.UUID, flow: FlowDefinition
) -> FlowReport:
    report = structure(flow)
    nodes = flow.nodes.items()

    wanted_prompts = {p for _, n in nodes for p in prompt_ids(n)}
    if wanted_prompts:
        found = set(
            await session.scalars(
                select(Prompt.id).where(
                    Prompt.tenant_id == tenant_id, Prompt.id.in_(wanted_prompts)
                )
            )
        )
        with_audio = set(
            await session.scalars(
                select(PromptAudio.prompt_id).where(PromptAudio.prompt_id.in_(found)).distinct()
            )
        )
        for node_id, node in nodes:
            for p in prompt_ids(node):
                if p not in found:
                    report.errors.append(f"{node_id}: prompt {p} does not exist")
                elif p not in with_audio:
                    report.errors.append(f"{node_id}: prompt {p} has no recording yet")

    numbers = set(
        await session.scalars(
            select(Extension.number).where(Extension.tenant_id == tenant_id, Extension.enabled)
        )
    )
    queues = set(await session.scalars(select(Queue.id).where(Queue.tenant_id == tenant_id)))
    for node_id, node in nodes:
        if isinstance(node, Voicemail) and node.mailbox not in numbers:
            report.errors.append(f"{node_id}: mailbox {node.mailbox} is not an extension")
        if isinstance(node, QueueNode) and node.queue not in queues:
            report.errors.append(f"{node_id}: queue {node.queue} does not exist")
        if isinstance(node, TimeCondition) and node.timezone:
            try:
                ZoneInfo(node.timezone)
            except (ZoneInfoNotFoundError, ValueError):
                report.errors.append(f"{node_id}: unknown timezone '{node.timezone}'")
    return report
