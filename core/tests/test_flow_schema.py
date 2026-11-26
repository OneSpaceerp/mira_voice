"""Mira Flow v1 format and wiring checks (no database)."""

import uuid
from typing import Any

import pytest
from pydantic import ValidationError

from mira_core.flows.schema import FlowDefinition, next_ids, template_variables
from mira_core.flows.validate import structure

P = str(uuid.uuid4())  # a prompt id


def flow(**nodes: dict[str, Any]) -> dict[str, Any]:
    return {"schema": "mira-flow/1", "start": next(iter(nodes)), "nodes": nodes}


GOOD = flow(
    welcome={"type": "play", "prompt": P, "next": "hours"},
    hours={
        "type": "time",
        "weekly": [{"days": ["sun", "mon", "tue", "wed", "thu"], "from": "09:00", "to": "17:00"}],
        "holidays": ["2026-12-25"],
        "open_next": "lang",
        "closed_next": "bye",
    },
    lang={"type": "menu", "prompt": P, "options": {"1": "ar", "2": "en"}, "invalid_next": "ar"},
    ar={"type": "language", "language": "ar", "next": "account"},
    en={"type": "language", "language": "en", "next": "account"},
    account={
        "type": "collect",
        "prompt": P,
        "variable": "account",
        "min_digits": 4,
        "max_digits": 10,
        "next": "lookup",
        "timeout_next": "agent",
    },
    lookup={
        "type": "http",
        "url": "https://erp.example.com/api/method/mira.lookup?account={{account}}&from={{caller_number}}",
        "extract": {"vip": "message.vip"},
        "next": "is_vip",
        "error_next": "agent",
    },
    is_vip={
        "type": "branch",
        "variable": "vip",
        "conditions": [{"op": "eq", "value": "1", "next": "vip_line"}],
        "default_next": "agent",
    },
    vip_line={"type": "transfer", "number": "1001"},
    agent={"type": "transfer", "number": "1002"},
    bye={"type": "voicemail", "mailbox": "1001", "greeting": P},
)


def test_a_full_flow_is_valid() -> None:
    parsed = FlowDefinition.model_validate(GOOD)
    report = structure(parsed)
    assert report.ok, report.errors
    assert report.warnings == []
    assert sorted(next_ids(parsed.nodes["lang"])) == ["ar", "ar", "en"]


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        ({"start": "Bad-Id"}, "start"),
        ({"schema": "mira-flow/9"}, "schema"),
        ({"nodes": {"x": {"type": "teleport", "next": "y"}}}, "type"),
        ({"nodes": {"x": {"type": "play", "prompt": "not-a-uuid", "next": "y"}}}, "prompt"),
        ({"nodes": {"x": {"type": "play", "prompt": P, "next": "y", "code": "rm -rf"}}}, "code"),
        (
            {
                "nodes": {
                    "x": {"type": "menu", "prompt": P, "options": {"12": "y"}, "invalid_next": "y"}
                }
            },
            "options",
        ),
        (
            {
                "nodes": {
                    "x": {
                        "type": "collect",
                        "prompt": P,
                        "variable": "pin",
                        "min_digits": 6,
                        "max_digits": 4,
                        "next": "y",
                        "timeout_next": "y",
                    }
                }
            },
            "min_digits",
        ),
        (
            {
                "nodes": {
                    "x": {
                        "type": "collect",
                        "prompt": P,
                        "variable": "caller_number",
                        "next": "y",
                        "timeout_next": "y",
                    }
                }
            },
            "built-in",
        ),
        (
            {
                "nodes": {
                    "x": {
                        "type": "time",
                        "weekly": [{"days": ["mon"], "from": "18:00", "to": "09:00"}],
                        "open_next": "y",
                        "closed_next": "y",
                    }
                }
            },
            "before",
        ),
        ({"nodes": {"x": {"type": "language", "language": "de", "next": "y"}}}, "language"),
        ({"nodes": {"x": {"type": "transfer", "number": "1001;evil"}}}, "number"),
        ({"nodes": {"x": {"type": "voicemail", "mailbox": "x1"}}}, "mailbox"),
    ],
)
def test_bad_nodes_are_rejected(change: dict[str, Any], fragment: str) -> None:
    data = {**GOOD, **change}
    if "nodes" in change:
        data["start"] = "x"
    with pytest.raises(ValidationError) as err:
        FlowDefinition.model_validate(data)
    assert fragment in str(err.value)


@pytest.mark.parametrize(
    "value",
    [
        "{{ account.__class__ }}",
        "{% for x in y %}",
        "{{account}} }}",
        "{{ account | upper }}",
        "line\nbreak",
    ],
)
def test_templates_hold_placeholders_only(value: str) -> None:
    node = {"type": "set", "variable": "x", "value": value, "next": "y"}
    with pytest.raises(ValidationError):
        FlowDefinition.model_validate(flow(s=node, y={"type": "hangup"}))


def test_template_variables() -> None:
    assert template_variables("a {{ one }} b {{two}} {{one}}") == {"one", "two"}


@pytest.mark.parametrize(
    "url",
    [
        "ftp://erp.example.com/x",
        "https://{{host}}/api",
        "https://user:pw@erp.example.com/api",
        "erp.example.com/api",
    ],
)
def test_data_dip_urls(url: str) -> None:
    node = {"type": "http", "url": url, "next": "y", "error_next": "y"}
    with pytest.raises(ValidationError):
        FlowDefinition.model_validate(flow(h=node, y={"type": "hangup"}))


def test_wiring_problems_are_reported() -> None:
    parsed = FlowDefinition.model_validate(
        flow(
            a={"type": "play", "prompt": P, "next": "missing"},
            b={"type": "set", "variable": "x", "value": "{{nobody_sets_this}}", "next": "b"},
            c={"type": "hangup"},
        )
    )
    report = structure(parsed)
    assert "a: goes to 'missing', which does not exist" in report.errors
    assert "b: goes to itself" in report.errors
    assert "b: variable 'nobody_sets_this' is never set" in report.errors
    assert sorted(report.warnings) == [
        "b: not reachable from the start",
        "c: not reachable from the start",
    ]


def test_json_schema_is_exported() -> None:
    schema = FlowDefinition.model_json_schema(by_alias=True)
    assert "schema" in schema["properties"] and "nodes" in schema["properties"]
