"""LangGraph SQLite checkpointer for the approval (interrupt/resume) flow.

M0: scaffold only. Filled in at M3. Uses a DB file separate from flinch.db
(flinch_checkpoints.db) — see NOTES.md "Open decisions" for the reasoning:
keeps LangGraph's own schema fully isolated from the hand-rolled
queue/pending_queue tables rather than risking a collision.
"""

from pathlib import Path

CHECKPOINT_DB_PATH = Path(__file__).parent.parent / "flinch_checkpoints.db"


def get_checkpointer():
    raise NotImplementedError("agent_deepagents.checkpointer: implemented in M3")
