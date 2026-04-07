import sqlite3
import json
import uuid
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "flinch.db"

def init_queue():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS queue (
            id          TEXT PRIMARY KEY,
            type        TEXT NOT NULL,
            source      TEXT NOT NULL,
            payload     TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'queued',
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def enqueue(type: str, source: str, payload: dict) -> str:
    event_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO queue VALUES (?, ?, ?, ?, 'queued', ?, ?)",
        (event_id, type, source, json.dumps(payload), now, now)
    )
    conn.commit()
    conn.close()
    print(f"[queue] enqueued {type} from {source} → {event_id}")
    return event_id

def dequeue() -> dict | None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM queue WHERE status = 'queued' ORDER BY created_at ASC LIMIT 1"
    ).fetchone()
    if not row:
        conn.close()
        return None
    now = datetime.utcnow().isoformat()
    conn.execute(
        "UPDATE queue SET status = 'in-progress', updated_at = ? WHERE id = ?",
        (now, row["id"])
    )
    conn.commit()
    conn.close()
    return {
        "id": row["id"],
        "type": row["type"],
        "source": row["source"],
        "payload": json.loads(row["payload"]),
        "created_at": row["created_at"]
    }

def complete(event_id: str):
    _update_status(event_id, "completed")
    print(f"[queue] completed → {event_id}")

def fail(event_id: str):
    _update_status(event_id, "failed")
    print(f"[queue] failed → {event_id}")

def _update_status(event_id: str, status: str):
    now = datetime.utcnow().isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE queue SET status = ?, updated_at = ? WHERE id = ?",
        (status, now, event_id)
    )
    conn.commit()
    conn.close()

def enqueue_pending(task_type: str, payload: dict, reason: str) -> str:
    task_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pending_queue (
            id         TEXT PRIMARY KEY,
            task_type  TEXT NOT NULL,
            payload    TEXT NOT NULL,
            reason     TEXT NOT NULL,
            status     TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    # Check for existing pending task for this email_id
    email_id = payload.get("email_id", "")
    if email_id:
        existing = conn.execute(
            "SELECT id FROM pending_queue WHERE payload LIKE ? AND status = 'pending'",
            (f'%"{email_id}"%',)
        ).fetchone()
        if existing:
            conn.close()
            print(f"  [pending] already queued → skipping duplicate for {email_id[:16]}...")
            return existing[0]

    conn.execute(
        "INSERT INTO pending_queue VALUES (?, ?, ?, ?, 'pending', ?, ?)",
        (task_id, task_type, json.dumps(payload), reason, now, now)
    )
    conn.commit()
    conn.close()
    return task_id

def get_pending_tasks() -> list:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pending_queue (
            id TEXT PRIMARY KEY, task_type TEXT, payload TEXT,
            reason TEXT, status TEXT DEFAULT 'pending',
            created_at TEXT, updated_at TEXT
        )
    """)
    rows = conn.execute(
        "SELECT * FROM pending_queue WHERE status = 'pending' ORDER BY created_at ASC"
    ).fetchall()
    conn.close()
    return [{"id": r["id"], "task_type": r["task_type"],
             "payload": json.loads(r["payload"]), "reason": r["reason"],
             "created_at": r["created_at"]} for r in rows]

def update_pending_status(task_id: str, status: str):
    now = datetime.utcnow().isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE pending_queue SET status = ?, updated_at = ? WHERE id = ?",
        (status, now, task_id)
    )
    conn.commit()
    conn.close()

def peek_all() -> list:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, type, source, status, created_at FROM queue ORDER BY created_at DESC LIMIT 20"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]