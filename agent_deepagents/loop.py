"""DeepAgents-backed agent loop — sibling to agent/loop.py.

M0: scaffold only. build_agent()/run_agent() are filled in per-role starting
M2 (email_reviewer pilot), generalized to all four roles in M4.
"""


def build_agent(role_name: str):
    raise NotImplementedError(f"agent_deepagents: '{role_name}' not yet migrated (M2/M4)")


def run_agent(event: dict) -> dict:
    role_name = event.get("type")
    print(f"[agent_deepagents] AGENT_BACKEND=deepagents but no role migrated yet "
          f"(event type: {role_name}) — no-op")
    return {
        "session_id": event["id"],
        "event_type": event["type"],
        "role":       "unmigrated",
        "payload":    event["payload"],
        "response":   "",
        "tool_calls": [],
        "tokens":     0,
    }
