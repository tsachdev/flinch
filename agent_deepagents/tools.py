"""Wraps existing roles/{role}/tools.py TOOL_REGISTRY callables as LangChain
tools, from the existing Anthropic-style TOOLS schema (input_schema JSON
Schema). Does not reimplement any tool body — every wrapped function still
calls straight into the existing TOOL_REGISTRY implementation (Gmail/Graph
API calls, memory/queue writes, etc.).
"""

import functools
from typing import Any

from pydantic import create_model
from langchain_core.tools import StructuredTool

from agent.loop import _truncate_result

_JSON_TYPE_MAP = {
    "string":  str,
    "integer": int,
    "number":  float,
    "boolean": bool,
    "array":   list,
    "object":  dict,
}


def _schema_to_pydantic(tool_name: str, input_schema: dict):
    properties = input_schema.get("properties", {}) or {}
    required = set(input_schema.get("required", []) or [])

    fields = {}
    for prop_name, prop_schema in properties.items():
        py_type = _JSON_TYPE_MAP.get(prop_schema.get("type"), str)
        fields[prop_name] = (py_type, ... if prop_name in required else None)

    model_name = "".join(part.capitalize() for part in tool_name.split("_")) + "Args"
    return create_model(model_name, **fields)


def _with_truncation(fn):
    """Match agent/loop.py's context-size behavior: large tool results (e.g.
    get_unread_emails' email list) get truncated before they reach the model,
    same as the legacy loop's per-tool-result truncation. Without this, a
    DeepAgents run would send meaningfully more tokens per call than legacy
    for the same tools — the exact regression guardrail #6 warns about."""
    @functools.wraps(fn)
    def _wrapped(**kwargs):
        return _truncate_result(fn(**kwargs))
    return _wrapped


def wrap_tool_registry(tools_schema: list[dict], tool_registry: dict) -> list[StructuredTool]:
    """tools_schema is a role's TOOLS list (Anthropic tool-schema format);
    tool_registry is the matching TOOL_REGISTRY dict of name -> callable."""
    wrapped = []
    for spec in tools_schema:
        name = spec["name"]
        fn = tool_registry.get(name)
        if fn is None:
            continue
        args_model = _schema_to_pydantic(name, spec.get("input_schema", {}))
        wrapped.append(StructuredTool.from_function(
            func=_with_truncation(fn),
            name=name,
            description=spec.get("description", ""),
            args_schema=args_model,
        ))
    return wrapped


def replace_tool(wrapped_tools: list[StructuredTool], name: str, fn, description: str,
                  args_schema) -> list[StructuredTool]:
    """Swap one tool's implementation (e.g. add_to_pending_queue -> the
    checkpoint-integrated version) while leaving the rest untouched."""
    replacement = StructuredTool.from_function(
        func=fn, name=name, description=description, args_schema=args_schema,
    )
    return [replacement if t.name == name else t for t in wrapped_tools]
