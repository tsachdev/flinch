"""Checkpoint/interrupt approval flow — the DeepAgents-era replacement for the
execution side of the legacy pending_queue mechanism.

Design note (why a hand-rolled 2-node graph, not DeepAgents' HITL middleware
on the main agent loop): wrapping the *whole* email_reviewer run with
`interrupt_on` would pause the entire batch the moment the first uncertain
email is queued, blocking every subsequent email in that run until a human
responds — a real behavioral regression versus today, where
`add_to_pending_queue` just enqueues and the agent keeps going through the
rest of the batch. So the interrupt lives in a tiny, separate, per-proposal
graph: invoking it always returns immediately (the interrupt fires on first
entry, before anything executes), and the *main* agent's
`add_to_pending_queue` tool call starts this graph, sees the immediate
interrupt, and returns a normal tool result — indistinguishable, from the
agent's point of view, from today's plain enqueue. Only the later, separate
resume (approve/reject) actually runs the underlying tool. Same decisions,
same batch-processing behavior, same token/latency profile for the main run
— the only new capability is that the pending action now survives a process
restart via the checkpointer, instead of living only in the pending_queue
row.
"""

from typing import Callable, TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command

from agent_deepagents.checkpointer import get_checkpointer

_EXECUTORS: dict[str, Callable[[dict], dict]] = {}


def register_executor(task_type: str, fn: Callable[[dict], dict]) -> None:
    """Register the real tool call to run on approval for a given task_type.

    fn receives the proposal payload (e.g. {"email_id": ..., "subject": ...,
    "sender": ...}) and returns the same shape the underlying tool normally
    returns (e.g. {"status": "trashed", "email_id": ...}).
    """
    _EXECUTORS[task_type] = fn


class ApprovalState(TypedDict):
    task_type: str
    payload: dict
    reason: str
    decision: dict | None
    result: dict | None


def _propose(state: ApprovalState) -> dict:
    decision = interrupt({
        "task_type": state["task_type"],
        "payload":   state["payload"],
        "reason":    state["reason"],
    })
    return {"decision": decision}


def _execute(state: ApprovalState) -> dict:
    decision = state.get("decision") or {}
    if decision.get("approved"):
        fn = _EXECUTORS.get(state["task_type"])
        if fn is None:
            return {"result": {"status": "error", "error": f"no executor for {state['task_type']}"}}
        return {"result": fn(state["payload"])}
    return {"result": {"status": "rejected", **state["payload"]}}


_graph = StateGraph(ApprovalState)
_graph.add_node("propose", _propose)
_graph.add_node("execute", _execute)
_graph.add_edge(START, "propose")
_graph.add_edge("propose", "execute")
_graph.add_edge("execute", END)

_compiled = None


def _get_compiled():
    global _compiled
    if _compiled is None:
        _compiled = _graph.compile(checkpointer=get_checkpointer())
    return _compiled


def start_approval(thread_id: str, task_type: str, payload: dict, reason: str) -> dict:
    """Start a proposal. Always returns immediately with the interrupt info —
    the underlying tool has NOT run yet."""
    config = {"configurable": {"thread_id": thread_id}}
    state: ApprovalState = {
        "task_type": task_type, "payload": payload, "reason": reason,
        "decision": None, "result": None,
    }
    result = _get_compiled().invoke(state, config=config)
    return result


def resume_approval(thread_id: str, approved: bool) -> dict:
    """Resume a paused proposal with a human decision. Runs the real tool
    call on approval. Safe to call after a process restart — the paused
    state was persisted to flinch_checkpoints.db when start_approval() ran."""
    config = {"configurable": {"thread_id": thread_id}}
    result = _get_compiled().invoke(Command(resume={"approved": approved}), config=config)
    return result.get("result", {})


def is_pending(thread_id: str) -> bool:
    """True if a proposal for this thread is still awaiting a decision."""
    config = {"configurable": {"thread_id": thread_id}}
    state = _get_compiled().get_state(config)
    return bool(state.next)


def reset():
    """Drop the cached compiled graph (e.g. after checkpointer.reset() /
    CHECKPOINT_DB_PATH change, for an isolated test/shadow-mode run)."""
    global _compiled
    _compiled = None
