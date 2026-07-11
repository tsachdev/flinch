"""Branches each event to the legacy or DeepAgents agent loop.

main.py imports run_agent from here instead of agent.loop directly, so the
AGENT_BACKEND flag controls which implementation handles an event without
main.py needing to know about the split.
"""

try:
    from config import AGENT_BACKEND
except ImportError:
    AGENT_BACKEND = "legacy"


def run_agent(event: dict) -> dict:
    if AGENT_BACKEND == "deepagents":
        from agent_deepagents.loop import run_agent as deepagents_run_agent
        return deepagents_run_agent(event)
    from agent.loop import run_agent as legacy_run_agent
    return legacy_run_agent(event)
