"""LangGraph SQLite checkpointer for the approval (interrupt/resume) flow.

Points at a DB file separate from flinch.db (flinch_checkpoints.db) rather
than reusing the event-queue database. Decision: LangGraph owns its own
checkpoint schema (writes, blobs, migrations) fully; keeping that isolated
from the hand-rolled queue/pending_queue tables avoids any risk of a
collision or of LangGraph's migrations touching tables it doesn't own.
The two databases are correlated only loosely, via the `_thread_id` stashed
in a pending_queue row's payload (see agent_deepagents/approval.py) — no
shared schema, so there's nothing to keep in sync.
"""

import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

CHECKPOINT_DB_PATH = Path(__file__).parent.parent / "flinch_checkpoints.db"

_saver = None


def get_checkpointer() -> SqliteSaver:
    global _saver
    if _saver is None:
        conn = sqlite3.connect(str(CHECKPOINT_DB_PATH), check_same_thread=False)
        _saver = SqliteSaver(conn)
        _saver.setup()
    return _saver


def reset():
    """Drop the cached saver so the next get_checkpointer() call reconnects
    (e.g. after CHECKPOINT_DB_PATH is repointed at a temp file for an
    isolated test/shadow-mode run)."""
    global _saver
    _saver = None
