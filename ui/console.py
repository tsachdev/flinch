from flask import Flask, jsonify, redirect, request
from pathlib import Path
from datetime import datetime, timedelta, timezone
import sqlite3
import sys
import html

sys.path.insert(0, str(Path(__file__).parent.parent))
from eventqueue.bus import get_pending_tasks, update_pending_status
from roles.email_reviewer.tools import delete_email

app = Flask(__name__)
DB_PATH   = Path(__file__).parent.parent / "gen_claw.db"
MEMORY_DIR = Path(__file__).parent.parent / "memory"

ROLES = ["support_agent", "store_concierge", "email_reviewer", "personal_assistant"]
ROLE_LABELS = {
    "support_agent":      "Support",
    "store_concierge":    "Store",
    "email_reviewer":     "Email",
    "personal_assistant": "Assistant",
}

def _now():
    return datetime.now(timezone.utc)

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

def get_sessions(role, days=7):
    sessions_dir = MEMORY_DIR / "roles" / role / "sessions"
    if not sessions_dir.exists():
        return []
    cutoff = _now() - timedelta(days=days)
    sessions = []
    for f in sorted(sessions_dir.glob("*.md"), reverse=True):
        try:
            ts_str = f.stem[:19].replace("-", ":")
            ts_str = ts_str[:10] + "T" + ts_str[11:]
            ts = datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc)
            if ts >= cutoff:
                content = f.read_text()
                sessions.append({
                    "timestamp": ts.strftime("%b %d %H:%M"),
                    "preview":   _extract_preview(content),
                })
        except Exception:
            pass
    return sessions[:20]

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
    for i, line in enumerate(lines):
        if line.startswith("## Agent summary") and i + 1 < len(lines):
            return lines[i + 1][:120]
    for line in lines:
        if not line.startswith("#") and len(line) > 20:
            return line[:120]
    return ""

def _status_color(status):
    return {
        "completed":   "#0f6e56",
        "queued":      "#b07d2a",
        "in-progress": "#185fa5",
        "failed":      "#a32d2d",
    }.get(status, "#888")

def _role_color(trigger):
    return {
        "support_ticket": "#534AB7",
        "store_event":    "#0f6e56",
        "cron":           "#185fa5",
        "message":        "#993556",
    }.get(trigger, "#888")

# ---------------------------------------------------------------------------
# Markdown → HTML (sections only — ## headings + bullet lists)
# ---------------------------------------------------------------------------

def _render_summary_md(content: str) -> str:
    sections = []
    current_heading = None
    current_items   = []

    def flush():
        if current_heading is None and not current_items:
            return
        items_html = "".join(
            f'<li>{html.escape(item)}</li>' for item in current_items
        )
        list_block = f'<ul class="sum-list">{items_html}</ul>' if items_html else ""
        heading_html = (
            f'<div class="sum-heading">{html.escape(current_heading)}</div>'
            if current_heading else ""
        )
        sections.append(f'<div class="sum-section">{heading_html}{list_block}</div>')

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            flush()
            current_heading = line[3:]
            current_items   = []
        elif line.startswith("- ") or line.startswith("* "):
            # strip leading bold markers like **Foo**:
            item = line[2:].replace("**", "")
            current_items.append(item)
        elif line.startswith("# "):
            # top-level title — skip
            pass
        elif line and current_heading is not None and not current_items:
            # prose paragraph under a heading (no bullets yet)
            current_items.append(line)

    flush()
    return "".join(sections) if sections else ""

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, sans-serif;
       background: #f5f5f3; color: #1a1a1a; font-size: 14px; }
:root { --card: #fff; --border: #e0e0dc; --muted: #888; --radius: 10px; }
.header { background: #1B2A4A; color: white; padding: 14px 24px;
          display: flex; align-items: center; gap: 12px; }
.header h1 { font-size: 1.1rem; font-weight: 600; }
.header .sub { font-size: 0.78rem; opacity: 0.6; margin-left: auto; }
.tabs { display: flex; gap: 2px; background: #1B2A4A; padding: 0 24px; }
.tab { padding: 10px 18px; font-size: 0.82rem; font-weight: 500;
       color: rgba(255,255,255,0.5); border: none; background: none;
       border-bottom: 2px solid transparent;
       text-decoration: none; display: inline-block; }
.tab.active { color: white; border-bottom-color: #5DCAA5; }
.tab .badge { background: #D85A30; color: white; border-radius: 10px;
              padding: 1px 6px; font-size: 0.7rem; margin-left: 5px; }
.body { padding: 20px 24px; max-width: 1100px; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.card { background: var(--card); border: 0.5px solid var(--border);
        border-radius: var(--radius); padding: 16px; margin-bottom: 16px; }
.card h3 { font-size: 0.82rem; font-weight: 600; color: var(--muted);
           text-transform: uppercase; letter-spacing: .04em; margin-bottom: 12px; }
/* sub-tabs */
.subtabs { display: flex; gap: 0; border-bottom: 1px solid var(--border);
           margin-bottom: 16px; }
.subtab { padding: 7px 16px; font-size: 0.82rem; font-weight: 500; color: var(--muted);
          text-decoration: none; border-bottom: 2px solid transparent;
          margin-bottom: -1px; }
.subtab.active { color: #1B2A4A; border-bottom-color: #1B2A4A; }
/* summary sections */
.sum-section { margin-bottom: 16px; }
.sum-heading { font-size: 0.82rem; font-weight: 700; color: #1B2A4A;
               text-transform: uppercase; letter-spacing: .03em;
               margin-bottom: 6px; }
.sum-list { list-style: none; padding: 0; }
.sum-list li { font-size: 0.82rem; color: #444; line-height: 1.6;
               padding: 3px 0 3px 12px; border-left: 2px solid #e0e0dc;
               margin-bottom: 4px; }
/* event feed */
.event-row { display: flex; align-items: center; gap: 8px;
             padding: 7px 0; border-bottom: 0.5px solid var(--border); font-size: 0.82rem; }
.event-row:last-child { border-bottom: none; }
.dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.event-type { font-weight: 500; flex: 1; }
.event-time { color: var(--muted); font-size: 0.75rem; }
.event-status { font-size: 0.72rem; font-weight: 600; padding: 2px 7px;
                border-radius: 6px; background: #f0f0ee; }
/* sessions */
.session-card { border: 0.5px solid var(--border); border-radius: 8px;
                padding: 12px; margin-bottom: 10px; background: var(--card); }
.session-ts { font-size: 0.75rem; color: var(--muted); margin-bottom: 4px; }
.session-preview { font-size: 0.82rem; line-height: 1.5; color: #444; }
/* pending */
.pending-card { border: 0.5px solid var(--border); border-radius: 8px;
                padding: 12px; margin-bottom: 10px; background: var(--card); }
.pending-sender  { font-size: 0.75rem; color: var(--muted); margin-bottom: 3px; }
.pending-subject { font-size: 0.88rem; font-weight: 500; margin-bottom: 4px; }
.pending-reason  { font-size: 0.78rem; color: #666; margin-bottom: 10px; }
.actions { display: flex; gap: 6px; flex-wrap: wrap; }
.btn { padding: 5px 14px; border-radius: 7px; border: 0.5px solid var(--border);
       font-size: 0.78rem; font-weight: 500; cursor: pointer;
       text-decoration: none; display: inline-block; background: white; color: #333; }
.btn-yes   { border-color: #0f6e56; color: #0f6e56; }
.btn-no    { border-color: #888;    color: #888; }
.btn-later { border-color: #b07d2a; color: #b07d2a; }
.btn:hover { opacity: 0.7; }
.btn-all { background: #1B2A4A; color: white; border-color: #1B2A4A; margin-bottom: 12px; }
/* stats */
.stat { text-align: center; padding: 12px; }
.stat-num   { font-size: 1.6rem; font-weight: 600; color: #1B2A4A; }
.stat-label { font-size: 0.75rem; color: var(--muted); margin-top: 2px; }
.empty { color: var(--muted); font-size: 0.82rem; padding: 20px 0; text-align: center; }
"""

# ---------------------------------------------------------------------------
# Page shell
# ---------------------------------------------------------------------------

def render_page(active_tab, content, pending_count):
    tabs = [
        ("overview",          "Overview",   ""),
        ("support_agent",     "Support",    ""),
        ("store_concierge",   "Store",      ""),
        ("email_reviewer",    "Email",
         f'<span class="badge">{pending_count}</span>' if pending_count else ""),
        ("personal_assistant","Assistant",  ""),
    ]
    tab_html = "".join(
        f'<a href="/{t}" class="tab{" active" if t == active_tab else ""}">{label}{badge}</a>'
        for t, label, badge in tabs
    )
    now = _now().strftime("%H:%M UTC")
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>gen-claw console</title>
<style>{CSS}</style>
<meta http-equiv="refresh" content="60">
</head><body>
<div class="header">
  <span style="font-size:1.3rem">🦞</span>
  <h1>gen-claw</h1>
  <span class="sub">auto-refresh every 60s &nbsp;·&nbsp; {now}</span>
</div>
<div class="tabs">{tab_html}</div>
<div class="body">{content}</div>
</body></html>"""

# ---------------------------------------------------------------------------
# Overview (unchanged)
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
        last_run_dt = datetime.fromisoformat(row[0]).replace(tzinfo=timezone.utc)
        last_run = last_run_dt.isoformat()
        next_run = (last_run_dt + timedelta(hours=2)).isoformat()

    return jsonify({
        "pending_count": len(pending),
        "last_run":  last_run,
        "next_run":  next_run,
    })


@app.route('/')
def root():
    return redirect('/overview')

@app.route('/overview')
def overview():
    events  = get_queue_events(30)
    pending = get_pending_tasks()
    today   = _now().strftime("%Y-%m-%d")

    role_counts = {}
    for role in ROLES:
        d = MEMORY_DIR / "roles" / role / "sessions"
        role_counts[role] = len(list(d.glob(f"{today}*.md"))) if d.exists() else 0

    stats_html = '<div class="grid2"><div class="card"><div style="display:flex;gap:0">'
    for role in ROLES:
        stats_html += f"""<div class="stat" style="flex:1">
          <div class="stat-num">{role_counts[role]}</div>
          <div class="stat-label">{ROLE_LABELS[role]}</div>
        </div>"""
    stats_html += '</div></div>'
    stats_html += f"""<div class="card"><div style="display:flex;gap:0">
      <div class="stat" style="flex:1">
        <div class="stat-num">{len([e for e in events if e["status"]=="completed"])}</div>
        <div class="stat-label">Completed</div>
      </div>
      <div class="stat" style="flex:1">
        <div class="stat-num">{len([e for e in events if e["status"]=="failed"])}</div>
        <div class="stat-label">Failed</div>
      </div>
      <div class="stat" style="flex:1">
        <div class="stat-num" style="color:#D85A30">{len(pending)}</div>
        <div class="stat-label">Pending</div>
      </div>
    </div></div></div>"""

    feed_rows = ""
    for e in events[:20]:
        color = _role_color(e["type"])
        sc    = _status_color(e["status"])
        ts    = e["created_at"][11:16]
        feed_rows += f"""<div class="event-row">
          <div class="dot" style="background:{color}"></div>
          <span class="event-type" style="color:{color}">{e["type"]}</span>
          <span style="color:#888;font-size:0.75rem">{e["source"]}</span>
          <span class="event-status" style="color:{sc}">{e["status"]}</span>
          <span class="event-time">{ts}</span>
        </div>"""

    content = stats_html
    content += f'<div class="card"><h3>Recent queue activity</h3>{feed_rows}</div>'
    return render_page("overview", content, len(pending))

# ---------------------------------------------------------------------------
# Role tabs — Summary / Actions sub-tabs
# ---------------------------------------------------------------------------

def role_tab(role):
    view     = request.args.get("view", "summary")
    sessions = get_sessions(role, days=7)
    summary  = get_latest_summary(role)
    pending  = get_pending_tasks() if role == "email_reviewer" else []
    base_url = f"/{role}"

    subtabs = (
        f'<div class="subtabs">'
        f'<a class="subtab{" active" if view == "summary" else ""}" href="{base_url}?view=summary">Summary</a>'
        f'<a class="subtab{" active" if view == "actions" else ""}" href="{base_url}?view=actions">Actions'
        + (f' <span class="badge" style="background:#D85A30">{len(pending)}</span>' if pending and role == "email_reviewer" else "")
        + '</a></div>'
    )

    if view == "summary":
        main_content = _render_summary_tab(role, sessions, summary)
    else:
        main_content = _render_actions_tab(role, pending)

    content = subtabs + main_content
    return render_page(role, content, len(get_pending_tasks()))


def _render_summary_tab(role, sessions, summary):
    html_parts = '<div class="grid2">'

    # Left: sessions
    sess_html = ""
    if sessions:
        for s in sessions[:10]:
            sess_html += f"""<div class="session-card">
              <div class="session-ts">{s["timestamp"]}</div>
              <div class="session-preview">{html.escape(s["preview"] or "—")}</div>
            </div>"""
    else:
        sess_html = '<div class="empty">No sessions this week</div>'
    html_parts += f'<div><div class="card"><h3>Sessions — last 7 days ({len(sessions)})</h3>{sess_html}</div></div>'

    # Right: parsed summary
    if summary:
        parsed = _render_summary_md(summary["content"])
        right = (
            f'<div class="card"><h3>Latest summary — {summary["date"]}</h3>'
            + (parsed or '<div class="empty">Summary is empty.</div>')
            + '</div>'
        )
    else:
        right = (
            '<div class="card"><div class="empty" style="padding:32px 0">'
            'No summary yet — the daily summarizer runs at midnight.'
            '</div></div>'
        )
    html_parts += f'<div>{right}</div>'
    html_parts += '</div>'
    return html_parts


def _render_actions_tab(role, pending):
    if role != "email_reviewer":
        return '<div class="card"><div class="empty" style="padding:32px 0">No actions pending.</div></div>'

    if not pending:
        return '<div class="card"><div class="empty" style="padding:32px 0">No pending approvals.</div></div>'

    bulk  = f'<a class="btn btn-all" href="/approve-all">Delete all ({len(pending)})</a>'
    cards = ""
    for t in pending:
        cards += f"""<div class="pending-card">
          <div class="pending-sender">{html.escape(t["payload"].get("sender",""))}</div>
          <div class="pending-subject">{html.escape(t["payload"].get("subject",""))}</div>
          <div class="pending-reason">{html.escape(t["reason"])}</div>
          <div class="actions">
            <a class="btn btn-yes"   href="/approve/{t["id"]}">Delete</a>
            <a class="btn btn-no"    href="/reject/{t["id"]}">Keep</a>
            <a class="btn btn-later" href="/later/{t["id"]}">Later</a>
          </div>
        </div>"""
    return f'<div class="card"><h3>Pending approvals ({len(pending)})</h3>{bulk}{cards}</div>'


@app.route('/support_agent')
def support_tab():   return role_tab("support_agent")

@app.route('/store_concierge')
def store_tab():     return role_tab("store_concierge")

@app.route('/email_reviewer')
def email_tab():     return role_tab("email_reviewer")

@app.route('/personal_assistant')
def assistant_tab(): return role_tab("personal_assistant")

# ---------------------------------------------------------------------------
# Approval actions
# ---------------------------------------------------------------------------

@app.route('/approve/<task_id>')
def approve(task_id):
    tasks = get_pending_tasks()
    task  = next((t for t in tasks if t['id'] == task_id), None)
    if task:
        try:
            delete_email(task['payload']['email_id'])
        except Exception as e:
            print(f"[console] delete error: {e}")
        update_pending_status(task_id, 'approved')
    return redirect('/email_reviewer?view=actions')

@app.route('/reject/<task_id>')
def reject(task_id):
    update_pending_status(task_id, 'rejected')
    return redirect('/email_reviewer?view=actions')

@app.route('/later/<task_id>')
def later(task_id):
    update_pending_status(task_id, 'later')
    return redirect('/email_reviewer?view=actions')

@app.route('/approve-all')
def approve_all():
    for task in get_pending_tasks():
        try:
            delete_email(task['payload']['email_id'])
            update_pending_status(task['id'], 'approved')
        except Exception as e:
            print(f"[console] bulk delete error: {e}")
    return redirect('/email_reviewer?view=actions')


if __name__ == '__main__':
    print("🦞 gen-claw console → http://localhost:5001")
    app.run(host='0.0.0.0', port=5001, debug=False)
