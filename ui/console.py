from flask import Flask, jsonify, redirect, request, send_from_directory
from pathlib import Path
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import json as json_lib
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from eventqueue.bus import get_pending_tasks, update_pending_status
from roles.email_reviewer.tools import delete_email

try:
    from config import DISPLAY_TIMEZONE
except ImportError:
    DISPLAY_TIMEZONE = "UTC"

app = Flask(__name__)
DB_PATH        = Path(__file__).parent.parent / "flinch.db"
MEMORY_DIR     = Path(__file__).parent.parent / "memory"
FRONTEND_DIST  = Path(__file__).parent.parent / "console-ui" / "dist"

ROLES = ["support_agent", "email_reviewer", "personal_assistant", "market_watcher"]
ROLE_LABELS = {
    "support_agent":      "Support",
    "email_reviewer":     "Email",
    "personal_assistant": "Assistant",
    "market_watcher":     "Market",
}

# Trigger types each role's queue events show up under (see agent/registry.py
# TRIGGER_TO_ROLE — kept in sync by hand since this is display-only).
ROLE_TRIGGER_TYPES = {
    "support_agent":      ["support_ticket"],
    "email_reviewer":     ["cron", "microsoft_email"],  # "cron" also carries daily_summary/market_watch jobs
    "personal_assistant": ["message"],
    "market_watcher":     ["market_event"],
}

# Fixed cron schedule from main.py's start_scheduler(), in UTC — used only to
# compute "next scheduled trigger" for the overview cards. support_agent and
# personal_assistant are event-driven (no fixed schedule).
SCHEDULE_UTC = {
    "email_reviewer": ["10:00", "14:00", "18:00", "22:00", "02:00"],
    "market_watcher": ["08:00"],
}

def _to_local(dt_utc: datetime) -> datetime:
    """Convert a UTC datetime to the configured display timezone."""
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    return dt_utc.astimezone(ZoneInfo(DISPLAY_TIMEZONE))

def _now():
    return _to_local(datetime.now(timezone.utc))

def _parse_utc_iso(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt

# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def get_queue_events(limit=30):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM queue ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def _role_events(role, limit=50):
    """Queue events belonging to a role, newest first."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    types = ROLE_TRIGGER_TYPES[role]
    placeholders = ",".join("?" for _ in types)
    rows = conn.execute(
        f"SELECT * FROM queue WHERE type IN ({placeholders}) ORDER BY created_at DESC LIMIT ?",
        (*types, limit)
    ).fetchall()
    conn.close()
    events = [dict(r) for r in rows]
    if role == "email_reviewer":
        def _is_email_job(e):
            if e["type"] == "microsoft_email":
                return True
            try:
                return json_lib.loads(e["payload"]).get("job") == "email_review"
            except (ValueError, TypeError):
                return False
        events = [e for e in events if _is_email_job(e)]
    return events

def _role_status(role):
    """(is_running, last_completed_run_iso_utc_or_None)"""
    events = _role_events(role, limit=10)
    running = any(e["status"] == "in-progress" for e in events)
    completed = [e for e in events if e["status"] == "completed"]
    last_run = completed[0]["created_at"] if completed else None
    return running, last_run

def _next_scheduled_run(role):
    times = SCHEDULE_UTC.get(role)
    if not times:
        return None
    now_utc = datetime.now(timezone.utc)
    candidates = []
    for t in times:
        hh, mm = map(int, t.split(":"))
        candidate = now_utc.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if candidate <= now_utc:
            candidate += timedelta(days=1)
        candidates.append(candidate)
    return _to_local(min(candidates)).isoformat()

def get_sessions(role, days=7):
    sessions_dir = MEMORY_DIR / "roles" / role / "sessions"
    if not sessions_dir.exists():
        return []
    sessions = []
    for f in sorted(sessions_dir.glob("*.md"), reverse=True):
        try:
            stem = f.stem
            date_part, time_part = stem.split("T")
            time_fixed = time_part.replace("-", ":")
            ts = datetime.fromisoformat(f"{date_part}T{time_fixed}").replace(tzinfo=timezone.utc)
            content = f.read_text()
            sessions.append({
                "timestamp": _to_local(ts).strftime("%b %d %H:%M"),
                "preview":   _extract_preview(content),
            })
        except Exception:
            pass
        if len(sessions) >= 5:
            break
    return sessions

def get_sessions_detailed(role, limit=20):
    """Richer session feed for the console SPA: timestamp (ISO, local tz),
    one-line summary, and the parsed 'Actions taken' list for the
    expandable tool-call detail view."""
    sessions_dir = MEMORY_DIR / "roles" / role / "sessions"
    if not sessions_dir.exists():
        return []
    items = []
    for f in sorted(sessions_dir.glob("*.md"), reverse=True)[:limit]:
        try:
            stem = f.stem
            date_part, time_part = stem.split("T")
            time_fixed = time_part.replace("-", ":")
            ts = datetime.fromisoformat(f"{date_part}T{time_fixed}").replace(tzinfo=timezone.utc)
        except Exception:
            ts = None
        content = f.read_text()
        items.append({
            "timestamp": _to_local(ts).isoformat() if ts else None,
            "preview":   _extract_preview(content),
            "actions":   _parse_session_actions(content),
        })
    return items

def get_latest_summary(role):
    summaries_dir = MEMORY_DIR / "roles" / role / "summaries"
    if not summaries_dir.exists():
        return None
    files = sorted(summaries_dir.glob("*.md"), reverse=True)
    if files:
        return {"date": files[0].stem, "content": files[0].read_text()}
    return None

def _extract_preview(content):
    lines = [l.strip() for l in content.splitlines() if l.strip()]

    # Prefer Console summary — clean LLM-generated 2-sentence summary
    in_console = False
    for line in lines:
        if line.startswith("## Console summary"):
            in_console = True
            continue
        if in_console:
            if line.startswith("#") or line.startswith("---"):
                break
            clean = line.replace("**", "").replace("*", "").strip()
            if len(clean) > 10:
                return clean

    # Fall back to Agent summary extraction
    summary_lines = []
    in_summary = False
    for line in lines:
        if line.startswith("## Agent summary"):
            in_summary = True
            continue
        if in_summary:
            if line.startswith("---") or line.startswith("#"):
                continue
            clean = line.replace("**", "").replace("*", "").strip()
            if len(clean) > 10 and not clean.startswith("tokens:") and not clean.startswith("timestamp:"):
                summary_lines.append(clean[:100])
            if len(summary_lines) >= 3:
                break

    if summary_lines:
        return " · ".join(summary_lines)

    # Final fallback
    for line in lines:
        if (not line.startswith("#") and not line.startswith("---")
                and not line.startswith("type:") and not line.startswith("session_id:")
                and not line.startswith("payload.") and len(line) > 20):
            return line.replace("**", "")[:120]
    return ""

def _parse_session_actions(content: str) -> list:
    """Pull the '## Actions taken' numbered list out of a session note, e.g.
    '1. `delete_email({"email_id": "..."})` -> {"status": "trashed", ...}'.
    Returned as-is (already human-readable) for the console's expandable
    tool-call detail view."""
    lines = content.splitlines()
    in_section = False
    actions = []
    for line in lines:
        if line.strip().startswith("## Actions taken"):
            in_section = True
            continue
        if in_section:
            if line.startswith("##") or line.startswith("---"):
                break
            stripped = line.strip()
            if stripped:
                actions.append(stripped)
    return actions

# ---------------------------------------------------------------------------
# Approval execution — shared by the legacy GET routes (kept for
# mcp_server.py) and the new JSON API routes (used by the console SPA).
#
# A pending_queue row created by the DeepAgents backend carries a
# `_thread_id` in its payload (see agent_deepagents/loop.py's
# add_to_pending_queue replacement) — approving/rejecting it resumes the
# checkpointed proposal graph, which is what actually runs (or skips) the
# real delete_email/microsoft delete call. Rows without a `_thread_id`
# were created by the legacy backend and keep the original direct-call
# behavior. Same code path handles both eras' rows.
# ---------------------------------------------------------------------------

def _execute_approval(task: dict, approved: bool) -> dict:
    thread_id = task['payload'].get('_thread_id')
    if thread_id:
        from agent_deepagents.approval import resume_approval
        return resume_approval(thread_id, approved=approved)
    if not approved:
        return {"status": "rejected"}
    if task['task_type'] == 'delete_email_microsoft':
        from roles.email_reviewer.microsoft_tools import delete_email as ms_delete
        return ms_delete(task['payload']['email_id'])
    return delete_email(task['payload']['email_id'])

# ---------------------------------------------------------------------------
# MCP-server-facing JSON API — contracts must not change (mcp_server.py
# calls these exact paths). See docs/adding-a-role.md / NOTES.md.
# ---------------------------------------------------------------------------

@app.route('/api/status')
def api_status():
    pending = get_pending_tasks()

    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT created_at FROM queue WHERE type = 'cron' AND status = 'completed'"
        " ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    conn.close()

    last_run = next_run = None
    if row:
        last_run_dt = _parse_utc_iso(row[0])
        last_run = last_run_dt.isoformat()
        next_run = (last_run_dt + timedelta(hours=2)).isoformat()

    return jsonify({
        "pending_count": len(pending),
        "last_run":  last_run,
        "next_run":  next_run,
    })

@app.route('/api/email-summary')
def api_email_summary():
    summary = get_latest_summary("email_reviewer")
    sessions = get_sessions("email_reviewer", days=3)
    return jsonify({
        "summary": summary["content"] if summary else None,
        "summary_date": summary["date"] if summary else None,
        "recent_sessions": [{"timestamp": s["timestamp"], "preview": s["preview"]} for s in sessions[:5]],
    })

@app.route('/api/market-summary')
def api_market_summary():
    summary = get_latest_summary("market_watcher")
    sessions = get_sessions("market_watcher", days=3)
    return jsonify({
        "summary": summary["content"] if summary else None,
        "summary_date": summary["date"] if summary else None,
        "recent_sessions": [{"timestamp": s["timestamp"], "preview": s["preview"]} for s in sessions[:5]],
    })

@app.route('/api/pending')
def api_pending():
    pending = get_pending_tasks()
    items = []
    for t in pending:
        items.append({
            "id": t["id"],
            "sender": t["payload"].get("sender", ""),
            "subject": t["payload"].get("subject", ""),
            "reason": t.get("reason", ""),
            "source": "outlook" if t["task_type"] == "delete_email_microsoft" else "gmail",
            "created_at": t["created_at"],
        })
    return jsonify({"pending": items, "count": len(items)})

@app.route('/api/watchlist')
def api_watchlist():
    import csv
    portfolio_path = Path(__file__).parent.parent / "portfolio.csv"
    stocks = []
    if portfolio_path.exists():
        with open(portfolio_path) as f:
            for row in csv.DictReader(f):
                sym = row.get("Symbol", "").strip()
                if sym:
                    stocks.append({
                        "symbol": sym,
                        "price": row.get("Current Price", ""),
                        "change": row.get("Change", ""),
                    })
    return jsonify({"stocks": stocks})

@app.route('/update-skill/<role>', methods=['POST'])
def update_skill(role):
    import google.genai as genai
    from config import GOOGLE_API_KEY

    data = request.get_json()
    feedback = data.get('feedback', '').strip()
    if not feedback:
        return jsonify({'status': 'error', 'error': 'No feedback provided'})

    role_skill = Path(__file__).parent.parent / "skills" / "roles" / role
    skill_files = list(role_skill.glob("*.md")) if role_skill.exists() else []
    if not skill_files:
        return jsonify({'status': 'error', 'error': 'Skill file not found'})

    triage_file = skill_files[0]
    current_skill = triage_file.read_text()

    client = genai.Client(api_key=GOOGLE_API_KEY)
    response = client.models.generate_content(
        model="models/gemma-4-26b-a4b-it",
        contents=f"""You are updating an agent skill file based on user feedback.

Current skill file:
{current_skill}

User feedback:
{feedback}

Rewrite the skill file incorporating the feedback. Keep the YAML frontmatter unchanged.
Keep the overall structure. Only update the rules and special cases to reflect the feedback.
Return only the updated skill file content, nothing else."""
    )

    updated_skill = response.text
    triage_file.write_text(updated_skill)
    print(f"[console] skill updated for {role} — feedback: {feedback[:60]}...")

    # Auto-commit the skill change
    import subprocess
    repo_root = Path(__file__).parent.parent
    try:
        subprocess.run(["git", "add", str(triage_file)], cwd=repo_root, check=True)
        subprocess.run(
            ["git", "commit", "-m", f"skill: update {role} triage via console feedback"],
            cwd=repo_root, check=True
        )
        print(f"[console] skill committed to git")
    except subprocess.CalledProcessError as e:
        print(f"[console] git commit failed (non-fatal): {e}")

    return jsonify({'status': 'ok'})

# ---------------------------------------------------------------------------
# Legacy GET approval routes — kept unchanged in behavior for
# mcp_server.py's approve_email/reject_email tools, which call these exact
# paths. Redirect target updated from the retired /email_reviewer page to
# the new SPA root.
# ---------------------------------------------------------------------------

@app.route('/approve/<task_id>')
def approve(task_id):
    tasks = get_pending_tasks()
    task  = next((t for t in tasks if t['id'] == task_id), None)
    if task:
        try:
            _execute_approval(task, approved=True)
        except Exception as e:
            print(f"[console] delete error: {e}")
        update_pending_status(task_id, 'approved')
    return redirect('/')

@app.route('/reject/<task_id>')
def reject(task_id):
    tasks = get_pending_tasks()
    task  = next((t for t in tasks if t['id'] == task_id), None)
    if task:
        try:
            _execute_approval(task, approved=False)
        except Exception as e:
            print(f"[console] reject error: {e}")
    update_pending_status(task_id, 'rejected')
    return redirect('/')

@app.route('/later/<task_id>')
def later(task_id):
    update_pending_status(task_id, 'later')
    return redirect('/')

@app.route('/bulk-approve')
def bulk_approve():
    ids = request.args.get('ids', '').split(',')
    for task_id in ids:
        if not task_id: continue
        tasks = get_pending_tasks()
        task = next((t for t in tasks if t['id'] == task_id), None)
        if task:
            try:
                _execute_approval(task, approved=True)
            except Exception as e:
                print(f"[console] bulk approve error: {e}")
            update_pending_status(task_id, 'approved')
    return redirect('/')

@app.route('/bulk-reject')
def bulk_reject():
    ids = request.args.get('ids', '').split(',')
    for task_id in ids:
        if not task_id: continue
        tasks = get_pending_tasks()
        task = next((t for t in tasks if t['id'] == task_id), None)
        if task:
            try:
                _execute_approval(task, approved=False)
            except Exception as e:
                print(f"[console] bulk reject error: {e}")
        update_pending_status(task_id, 'rejected')
    return redirect('/')

@app.route('/bulk-later')
def bulk_later():
    ids = request.args.get('ids', '').split(',')
    for task_id in ids:
        if task_id:
            update_pending_status(task_id, 'later')
    return redirect('/')

@app.route('/approve-all')
def approve_all():
    for task in get_pending_tasks():
        try:
            _execute_approval(task, approved=True)
            update_pending_status(task['id'], 'approved')
        except Exception as e:
            print(f"[console] bulk delete error: {e}")
    return redirect('/')

# ---------------------------------------------------------------------------
# Console SPA-facing JSON API
# ---------------------------------------------------------------------------

@app.route('/api/roles')
def api_roles():
    today = _now().strftime("%Y-%m-%d")
    result = []
    for role in ROLES:
        running, last_run = _role_status(role)
        sessions = get_sessions(role, days=1)
        today_count = len(list((MEMORY_DIR / "roles" / role / "sessions").glob(f"{today}*.md"))) \
            if (MEMORY_DIR / "roles" / role / "sessions").exists() else 0
        result.append({
            "role": role,
            "label": ROLE_LABELS[role],
            "status": "running" if running else "idle",
            "last_run": _to_local(_parse_utc_iso(last_run)).isoformat() if last_run else None,
            "next_run": _next_scheduled_run(role),
            "summary": (sessions[0]["preview"] if sessions else None) or "No activity yet.",
            "sessions_today": today_count,
        })
    return jsonify({"roles": result})

@app.route('/api/roles/<role>/sessions')
def api_role_sessions(role):
    if role not in ROLES:
        return jsonify({"error": "unknown role"}), 404
    limit = int(request.args.get('limit', 20))
    return jsonify({
        "role": role,
        "sessions": get_sessions_detailed(role, limit=limit),
        "latest_summary": get_latest_summary(role),
    })

@app.route('/api/pending/<task_id>/approve', methods=['POST'])
def api_pending_approve(task_id):
    tasks = get_pending_tasks()
    task  = next((t for t in tasks if t['id'] == task_id), None)
    if not task:
        return jsonify({"status": "error", "error": "not found"}), 404
    try:
        _execute_approval(task, approved=True)
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500
    update_pending_status(task_id, 'approved')
    return jsonify({"status": "ok"})

@app.route('/api/pending/<task_id>/reject', methods=['POST'])
def api_pending_reject(task_id):
    tasks = get_pending_tasks()
    task  = next((t for t in tasks if t['id'] == task_id), None)
    if task:
        try:
            _execute_approval(task, approved=False)
        except Exception as e:
            return jsonify({"status": "error", "error": str(e)}), 500
    update_pending_status(task_id, 'rejected')
    return jsonify({"status": "ok"})

@app.route('/api/pending/bulk', methods=['POST'])
def api_pending_bulk():
    data = request.get_json() or {}
    action = data.get('action')
    ids = data.get('ids', [])
    if action not in ('approve', 'reject', 'later'):
        return jsonify({"status": "error", "error": "invalid action"}), 400

    tasks_by_id = {t['id']: t for t in get_pending_tasks()}
    for task_id in ids:
        task = tasks_by_id.get(task_id)
        if action == 'approve' and task:
            try:
                _execute_approval(task, approved=True)
            except Exception as e:
                print(f"[console] bulk approve error: {e}")
            update_pending_status(task_id, 'approved')
        elif action == 'reject':
            if task:
                try:
                    _execute_approval(task, approved=False)
                except Exception as e:
                    print(f"[console] bulk reject error: {e}")
            update_pending_status(task_id, 'rejected')
        elif action == 'later':
            update_pending_status(task_id, 'later')
    return jsonify({"status": "ok"})

# ---------------------------------------------------------------------------
# Serve the built SPA (console-ui/, `npm run build` -> console-ui/dist)
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    return send_from_directory(FRONTEND_DIST, 'index.html')

@app.route('/<path:path>')
def static_proxy(path):
    candidate = FRONTEND_DIST / path
    if candidate.exists() and candidate.is_file():
        return send_from_directory(FRONTEND_DIST, path)
    return send_from_directory(FRONTEND_DIST, 'index.html')


if __name__ == '__main__':
    print("🦞 Flinch console → http://localhost:5001")
    app.run(host='0.0.0.0', port=5001, debug=False)
