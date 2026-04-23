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
DB_PATH   = Path(__file__).parent.parent / "flinch.db"
MEMORY_DIR = Path(__file__).parent.parent / "memory"

ROLES = ["support_agent", "email_reviewer", "personal_assistant", "market_watcher"]
ROLE_LABELS = {
    "support_agent":      "Support",
    "email_reviewer":     "Email",
    "personal_assistant": "Assistant",
    "market_watcher":     "Market",
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
    sessions = []
    for f in sorted(sessions_dir.glob("*.md"), reverse=True):
        try:
            stem = f.stem
            date_part, time_part = stem.split("T")
            time_fixed = time_part.replace("-", ":")
            ts = datetime.fromisoformat(f"{date_part}T{time_fixed}").replace(tzinfo=timezone.utc)
            content = f.read_text()
            sessions.append({
                "timestamp": ts.strftime("%b %d %H:%M"),
                "preview":   _extract_preview(content),
            })
        except Exception:
            pass
        if len(sessions) >= 5:
            break
    return sessions

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

    summary_lines = []
    in_summary = False
    for line in lines:
        if line.startswith("## Agent summary"):
            in_summary = True
            continue
        if in_summary:
            # Skip sub-headings and separators but don't stop
            if line.startswith("---") or line.startswith("#"):
                continue
            clean = line.replace("**", "").replace("*", "").strip()
            if len(clean) > 10 and not clean.startswith("tokens:") and not clean.startswith("timestamp:"):
                summary_lines.append(clean[:100])
            if len(summary_lines) >= 3:
                break

    if summary_lines:
        return " · ".join(summary_lines)

    # Fallback: first meaningful non-metadata line
    for line in lines:
        if (not line.startswith("#") and not line.startswith("---")
                and not line.startswith("type:") and not line.startswith("session_id:")
                and not line.startswith("payload.") and len(line) > 20):
            return line.replace("**", "")[:120]
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
        "cron":           "#185fa5",
        "message":        "#993556",
        "market_event":   "#b07d2a",
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
.pending-card.selected { border-color: #1B2A4A; background: #f0f4f9; }
.pending-header { display: flex; align-items: flex-start; gap: 10px; }
.pending-check { margin-top: 2px; accent-color: #1B2A4A; width: 15px; height: 15px; cursor: pointer; flex-shrink: 0; }
.pending-sender  { font-size: 0.75rem; color: var(--muted); margin-bottom: 3px; }
.pending-subject { font-size: 0.88rem; font-weight: 500; margin-bottom: 4px; }
.pending-source  { font-size: 0.75rem; color: #888; margin-bottom: 4px; }
.pending-reason  { font-size: 0.78rem; color: #666; margin-bottom: 10px; }
.bulk-bar { display: flex; gap: 8px; align-items: center; margin-bottom: 14px; flex-wrap: wrap; }
.bulk-bar label { font-size: 0.8rem; color: var(--muted); display: flex; align-items: center; gap: 6px; cursor: pointer; }
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
        ("email_reviewer",    "Email",
         f'<span class="badge">{pending_count}</span>' if pending_count else ""),
        ("personal_assistant","Assistant",  ""),
        ("market_watcher",    "Market",     ""),
    ]
    tab_html = "".join(
        f'<a href="/{t}" class="tab{" active" if t == active_tab else ""}">{label}{badge}</a>'
        for t, label, badge in tabs
    )
    now = _now().strftime("%H:%M UTC")
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Flinch console</title>
<style>{CSS}</style>
<meta http-equiv="refresh" content="60">
</head><body>
<div class="header">
  <span style="font-size:1.3rem">🦞</span>
  <h1>Flinch</h1>
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
              <div class="session-preview" style="line-height:1.6">{html.escape(s["preview"] or "—")}</div>
            </div>"""
    else:
        sess_html = '<div class="empty">No sessions this week</div>'
    html_parts += f'<div><div class="card"><h3>Last 5 sessions</h3>{sess_html}</div></div>'

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
    html_parts += '</div>'  # closes grid2

    if role == "email_reviewer":
        html_parts += f"""
        <div class="card" style="margin-top:16px">
          <h3>Update email review behaviour</h3>
          <p style="font-size:0.82rem;color:#666;margin-bottom:12px">
            Describe what you want the agent to do differently. The skill file will be updated automatically.
          </p>
          <textarea id="skill-feedback" rows="3"
            style="width:100%;font-size:0.82rem;padding:8px;border:0.5px solid var(--border);
                   border-radius:6px;resize:vertical;font-family:inherit"
            placeholder="e.g. Don't flag Chamath newsletters as junk — I want to keep those"></textarea>
          <div style="margin-top:8px;display:flex;align-items:center;gap:12px">
            <a class="btn btn-yes" href="#" onclick="submitFeedback()">Update skill</a>
            <span id="feedback-status" style="font-size:0.78rem;color:#666"></span>
          </div>
        </div>
        <script>
        function submitFeedback() {{
            const feedback = document.getElementById('skill-feedback').value.trim();
            if (!feedback) {{ alert('Please enter some feedback first.'); return; }}
            document.getElementById('feedback-status').textContent = 'Updating...';
            fetch('/update-skill/email_reviewer', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{feedback: feedback}})
            }})
            .then(r => r.json())
            .then(data => {{
                if (data.status === 'ok') {{
                    document.getElementById('feedback-status').textContent = '✓ Skill updated';
                    document.getElementById('skill-feedback').value = '';
                }} else {{
                    document.getElementById('feedback-status').textContent = '✗ ' + data.error;
                }}
            }})
            .catch(() => {{
                document.getElementById('feedback-status').textContent = '✗ Request failed';
            }});
        }}
        </script>"""

    return html_parts


def _render_actions_tab(role, pending):
    if role not in ("email_reviewer", "email_reviewer_microsoft"):
        return '<div class="card"><div class="empty" style="padding:32px 0">No actions pending.</div></div>'

    if not pending:
        return '<div class="card"><div class="empty" style="padding:32px 0">No pending approvals.</div></div>'

    cards = ""
    for t in pending:
        sender  = html.escape(t["payload"].get("sender", ""))
        subject = html.escape(t["payload"].get("subject", ""))
        source  = "Microsoft Outlook" if t["task_type"] == "delete_email_microsoft" else "Gmail"
        date_str = t["created_at"][5:16].replace("T", " ")
        cards += f"""<div class="pending-card" id="card-{t['id']}">
          <div class="pending-header">
            <input type="checkbox" class="pending-check" id="chk-{t['id']}"
                   onchange="toggleCard('{t['id']}', this.checked)">
            <div style="flex:1">
              <div class="pending-sender">{sender} &nbsp;·&nbsp; {date_str}</div>
              <div class="pending-subject">{subject}</div>
              <div class="pending-source">📬 {source}</div>
              <div class="pending-reason">{html.escape(t['reason'])}</div>
              <div class="actions">
                <a class="btn btn-yes"   href="/approve/{t['id']}">Delete</a>
                <a class="btn btn-no"    href="/reject/{t['id']}">Keep</a>
                <a class="btn btn-later" href="/later/{t['id']}">Later</a>
              </div>
            </div>
          </div>
        </div>"""

    bulk_bar = f"""
    <div class="bulk-bar">
      <label><input type="checkbox" id="select-all" onchange="selectAll(this.checked)"> Select all</label>
      <a class="btn btn-yes"   href="#" onclick="bulkAction('approve')">Delete selected</a>
      <a class="btn btn-no"    href="#" onclick="bulkAction('reject')">Keep selected</a>
      <a class="btn btn-later" href="#" onclick="bulkAction('later')">Later selected</a>
      <span id="sel-count" style="font-size:0.78rem;color:var(--muted);margin-left:4px"></span>
    </div>
    <script>
    function toggleCard(id, checked) {{
      document.getElementById('card-'+id).classList.toggle('selected', checked);
      updateCount();
    }}
    function selectAll(checked) {{
      document.querySelectorAll('.pending-check').forEach(c => {{
        c.checked = checked;
        toggleCard(c.id.replace('chk-',''), checked);
      }});
    }}
    function updateCount() {{
      const n = document.querySelectorAll('.pending-check:checked').length;
      document.getElementById('sel-count').textContent = n ? n + ' selected' : '';
    }}
    function bulkAction(action) {{
      const ids = [...document.querySelectorAll('.pending-check:checked')].map(c => c.id.replace('chk-',''));
      if (!ids.length) {{ alert('Select at least one email first.'); return; }}
      window.location = '/bulk-' + action + '?ids=' + ids.join(',');
    }}
    </script>"""

    return f'<div class="card"><h3>Pending approvals ({len(pending)})</h3>{bulk_bar}{cards}</div>'


@app.route('/support_agent')
def support_tab():   return role_tab("support_agent")

@app.route('/email_reviewer')
def email_tab():     return role_tab("email_reviewer")

@app.route('/personal_assistant')
def assistant_tab(): return role_tab("personal_assistant")

@app.route('/market_watcher')
def market_tab():    return role_tab("market_watcher")

# ---------------------------------------------------------------------------
# Approval actions
# ---------------------------------------------------------------------------

@app.route('/approve/<task_id>')
def approve(task_id):
    tasks = get_pending_tasks()
    task  = next((t for t in tasks if t['id'] == task_id), None)
    if task:
        try:
            if task['task_type'] == 'delete_email_microsoft':
                from roles.email_reviewer.microsoft_tools import delete_email as ms_delete
                ms_delete(task['payload']['email_id'])
            else:
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

@app.route('/bulk-approve')
def bulk_approve():
    ids = request.args.get('ids', '').split(',')
    for task_id in ids:
        if not task_id: continue
        tasks = get_pending_tasks()
        task = next((t for t in tasks if t['id'] == task_id), None)
        if task:
            try:
                if task['task_type'] == 'delete_email_microsoft':
                    from roles.email_reviewer.microsoft_tools import delete_email as ms_delete
                    ms_delete(task['payload']['email_id'])
                else:
                    delete_email(task['payload']['email_id'])
            except Exception as e:
                print(f"[console] bulk approve error: {e}")
            update_pending_status(task_id, 'approved')
    return redirect('/email_reviewer?view=actions')

@app.route('/bulk-reject')
def bulk_reject():
    ids = request.args.get('ids', '').split(',')
    for task_id in ids:
        if task_id:
            update_pending_status(task_id, 'rejected')
    return redirect('/email_reviewer?view=actions')

@app.route('/bulk-later')
def bulk_later():
    ids = request.args.get('ids', '').split(',')
    for task_id in ids:
        if task_id:
            update_pending_status(task_id, 'later')
    return redirect('/email_reviewer?view=actions')

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
    return jsonify({'status': 'ok'})

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
    print("🦞 Flinch console → http://localhost:5001")
    app.run(host='0.0.0.0', port=5001, debug=False)
