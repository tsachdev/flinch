import sqlite3
import json
import uuid
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "gen_claw.db"

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

def peek_all() -> list:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, type, source, status, created_at FROM queue ORDER BY created_at DESC LIMIT 20"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]