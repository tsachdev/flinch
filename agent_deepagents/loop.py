"""DeepAgents-era agent loop — sibling to agent/loop.py.

M2: email_reviewer pilot (both the Gmail and Microsoft tool variants).
Reuses the exact persona/tools/skills/memory plumbing the legacy loop uses
(agent.registry.get_role, agent.context.build_context, agent.loop's
message-building and truncation helpers) so behavior parity is a matter of
handing the LLM the same system prompt and the same tools, not of
re-deriving any of that plumbing. M4 generalizes this to the other roles.

Uses langchain.agents.create_agent, not deepagents.create_deep_agent.
Measured finding during M2: create_deep_agent's FilesystemMiddleware and
SubAgentMiddleware are "protected scaffolding" — wired into every model
call unconditionally, and NOT removable via excluded_tools/
excluded_middleware, even when every filesystem/todo/subagent tool is
hidden from the model. On the email_reviewer shadow fixture this cost
~40-55% more tokens per run than legacy for the identical decision — over
guardrail #6's ~20% budget. None of Flinch's roles are narrow, single-
purpose event handlers that need that scaffolding, so — per explicit
sign-off — this loop uses create_agent, the lighter-weight primitive
create_deep_agent itself is built on. It keeps everything the spec actually
wanted from DeepAgents (LangGraph checkpoint/interrupt, LangChain
middleware for provider fallback) without the deep-agent harness tax. The
`deepagents` package is not a runtime dependency of this module as a
result — see NOTES.md.
"""

import uuid

from langchain.agents import create_agent

from agent.registry import get_role
from agent.context import build_context
from agent.loop import _build_user_message
from agent_deepagents import approval, graduation
from agent_deepagents.providers import get_model_and_middleware
from agent_deepagents.tools import wrap_tool_registry, replace_tool, _schema_to_pydantic


def _register_email_reviewer_executors():
    """task_type -> the real deletion call, so agent_deepagents.approval can
    run it on resume-approve. Only email_reviewer has an approval step
    today (support_agent/personal_assistant tools execute directly,
    market_watcher has none at all — see NOTES.md)."""
    from roles.email_reviewer import tools as gmail_tools
    from roles.email_reviewer import microsoft_tools

    approval.register_executor(
        "delete_email",
        lambda payload: gmail_tools.TOOL_REGISTRY["delete_email"](email_id=payload["email_id"]),
    )
    approval.register_executor(
        "delete_email_microsoft",
        lambda payload: microsoft_tools.TOOL_REGISTRY["delete_email"](email_id=payload["email_id"]),
    )


_register_email_reviewer_executors()


def _make_pending_queue_tool(task_type: str):
    """Replacement for add_to_pending_queue: starts a checkpointed approval
    proposal instead of writing straight to pending_queue. The proposal
    interrupts immediately — before delete_email would actually run — so
    from the calling agent's point of view this returns exactly like the
    legacy tool and the batch keeps going (see agent_deepagents/approval.py
    for why the interrupt lives in its own tiny graph rather than on the
    main agent). Also mirrors the row into eventqueue.pending_queue so the
    console can list it the same way it lists legacy rows, carrying a
    `_thread_id` in the payload for the resume step (M3)."""
    def _fn(email_id: str, subject: str, sender: str, reason: str) -> dict:
        from roles.email_reviewer import idempotency

        def _run():
            from eventqueue.bus import enqueue_pending

            thread_id = str(uuid.uuid4())
            payload = {"email_id": email_id, "subject": subject, "sender": sender, "_thread_id": thread_id}
            approval.start_approval(thread_id, task_type, payload, reason)
            task_id = enqueue_pending(task_type, payload, reason)
            return {"status": "queued", "task_id": task_id, "email_id": email_id}
        # Same guard as the registry tools — the Jul 17-18 retry loop queued
        # duplicate proposals for the same email within one session.
        return idempotency.check_and_record("add_to_pending_queue", email_id, _run)
    return _fn


def build_agent(trigger_type: str, event: dict):
    """Build a fresh DeepAgent for this event. Not cached: the system prompt
    is event-specific (today's summary, matched entities, payload-selected
    skills), exactly like the legacy loop's build_context() call — there's
    nothing reusable to cache beyond what Python already reuses (module-level
    tool wiring)."""
    role = get_role(trigger_type)
    system_prompt = build_context(role, event)

    wrapped_tools = wrap_tool_registry(role["tools"], role["registry"])

    if role["name"] == "email_reviewer":
        task_type = "delete_email_microsoft" if trigger_type == "microsoft_email" else "delete_email"
        add_pending_spec = next(t for t in role["tools"] if t["name"] == "add_to_pending_queue")
        args_schema = _schema_to_pydantic("add_to_pending_queue", add_pending_spec["input_schema"])
        wrapped_tools = replace_tool(
            wrapped_tools, "add_to_pending_queue", _make_pending_queue_tool(task_type),
            add_pending_spec["description"], args_schema,
        )

    if graduation.enabled() and role["name"] == "email_reviewer":
        wrapped_tools = graduation.wrap_gated_tools(wrapped_tools, role, trigger_type)

    model, middleware = get_model_and_middleware(role)

    agent = create_agent(
        model=model,
        tools=wrapped_tools,
        system_prompt=system_prompt,
        middleware=middleware,
    )
    return agent, role


def run_agent(event: dict) -> dict:
    trigger_type = event["type"]
    agent, role = build_agent(trigger_type, event)

    user_message = _build_user_message(trigger_type, event["payload"])
    state = agent.invoke({"messages": [{"role": "user", "content": user_message}]})

    return _extract_result(state, event, role)


def _message_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(content) if content else ""


def _parse_tool_result(content):
    """Tool results come back as JSON-serialized strings (LangChain's
    ToolMessage serialization); parse back to a dict/list to match the
    legacy loop's shape, since memory.writer._upsert_entities/
    _extract_observations index into call['result'] as a dict for some
    roles' tools (e.g. support_agent's get_customer)."""
    text = _message_text(content)
    try:
        import json
        return json.loads(text)
    except (ValueError, TypeError):
        return text


def _extract_result(state: dict, event: dict, role: dict) -> dict:
    from langchain_core.messages import AIMessage, ToolMessage

    messages = state.get("messages", [])

    tool_calls_by_id = {}
    for msg in messages:
        if isinstance(msg, AIMessage):
            for tc in (msg.tool_calls or []):
                tool_calls_by_id[tc["id"]] = {"tool": tc["name"], "input": tc["args"]}

    all_tool_calls = []
    for msg in messages:
        if isinstance(msg, ToolMessage) and msg.tool_call_id in tool_calls_by_id:
            entry = tool_calls_by_id[msg.tool_call_id]
            entry["result"] = _parse_tool_result(msg.content)
            all_tool_calls.append(entry)

    final_text = ""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            text = _message_text(msg.content)
            if text.strip():
                final_text = text
                break

    total_tokens = 0
    for msg in messages:
        if isinstance(msg, AIMessage) and msg.usage_metadata:
            total_tokens += msg.usage_metadata.get("total_tokens", 0)

    return {
        "session_id": event["id"],
        "event_type": event["type"],
        "role":       role["name"],
        "payload":    event["payload"],
        "response":   final_text,
        "tool_calls": all_tool_calls,
        "tokens":     total_tokens,
    }
