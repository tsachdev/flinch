"""Leveled Graduation Ledger gate (execution-layer M3). DEV ONLY, env-gated.

Enabled by GRADUATION_PACK=/path/to/packs/<pack> (e.g. the execution-layer
repo's packs/email-triage). When enabled, build_agent replaces each gated
tool (the pack's action ids, e.g. delete_email / mark_read) with a call
into the FlinchAdapter gate: the pack's current level, not the model,
decides whether the call queues for approval (L0/L1), executes with a
notification (L2), or executes silently (L3). The legacy
add_to_pending_queue path is untouched; the model can still queue cases it
is uncertain about, exactly as before.

Queued proposals are mirrored into eventqueue.pending_queue with a
`_gl_thread_id` in the payload so the existing console lists them next to
legacy rows; ui/console.py resumes them through resume() below.

Requires `pip install -e ~/execution-layer` in this venv (dev instance
only; never installed on the droplet while constraint 4 stands).
"""

import os
from pathlib import Path

_adapter = None
_executor_source = None

LEDGER_DEFAULT = Path(__file__).parent.parent / "graduation_ledger.jsonl"
CHECKPOINT_DEFAULT = Path(__file__).parent.parent / "flinch_graduation_checkpoints.db"


def enabled() -> bool:
    return bool(os.environ.get("GRADUATION_PACK"))


def reset():
    """Drop the cached adapter (tests repoint the env vars)."""
    global _adapter, _executor_source
    _adapter = None
    _executor_source = None


def _notify(action, payload, result):
    print(f"  [graduation] L2 notify: {action}({payload.get('email_id', payload)}) "
          f"-> {result.get('status', result)}")


def get_adapter():
    global _adapter
    if _adapter is None:
        from adapters.flinch import FlinchAdapter

        pack = Path(os.environ["GRADUATION_PACK"])
        _adapter = FlinchAdapter(
            pack,
            Path(os.environ.get("GRADUATION_LEDGER", LEDGER_DEFAULT)),
            Path(os.environ.get("GRADUATION_CHECKPOINT_DB", CHECKPOINT_DEFAULT)),
            patterns_dir=pack.parent.parent / "patterns",
            notify=_notify,
        )
    return _adapter


def _register_executors(trigger_type: str):
    """Point gated actions at the right provider registry for this event.
    Looked up late (at execution time) so tests can patch TOOL_REGISTRY."""
    global _executor_source
    if trigger_type == "microsoft_email":
        from roles.email_reviewer import microsoft_tools as mod
    else:
        from roles.email_reviewer import tools as mod
    _executor_source = mod
    adapter = get_adapter()
    for action in list(adapter.ledger.rules.actions):
        def make(action_name):
            def _execute(payload):
                return _executor_source.TOOL_REGISTRY[action_name](**payload)
            return _execute
        adapter.register_executor(action, make(action))


def wrap_gated_tools(wrapped_tools, role, trigger_type):
    """Replace each pack-governed tool with the leveled gate. Everything the
    pack does not govern passes through untouched."""
    from agent_deepagents.tools import replace_tool, _schema_to_pydantic
    from eventqueue.bus import enqueue_pending

    adapter = get_adapter()
    _register_executors(trigger_type)

    for spec in role["tools"]:
        name = spec["name"]
        if not adapter.governs(name):
            continue

        def make_gated(action_name):
            def _fn(**kwargs) -> dict:
                result = get_adapter().gate(
                    action_name, kwargs,
                    reason=f"agent call at {get_adapter().ledger.level(action_name)}",
                )
                if result.get("status") == "queued":
                    payload = {**kwargs, "_gl_thread_id": result["thread_id"]}
                    task_id = enqueue_pending(action_name, payload,
                                              f"graduation gate ({result['level']})")
                    result["task_id"] = task_id
                return result
            return _fn

        args_schema = _schema_to_pydantic(name, spec.get("input_schema", {}))
        wrapped_tools = replace_tool(
            wrapped_tools, name, make_gated(name),
            spec.get("description", ""), args_schema,
        )
    return wrapped_tools


def resume(thread_id: str, approved: bool, reason: str | None = None) -> dict:
    """Console-facing resume for a graduation-queued proposal."""
    return get_adapter().resume(thread_id, approved, reason=reason)


def status() -> dict:
    """Level status + advisories for the console API."""
    adapter = get_adapter()
    return {
        "pack": adapter.ledger.rules.name,
        "promotion_mode": adapter.ledger.rules.promotion_mode,
        "actions": adapter.ledger.status(),
        "advisories": adapter.ledger.advisories(),
        "pending": adapter.pending(),
    }
