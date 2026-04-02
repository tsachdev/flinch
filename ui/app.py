import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, redirect, url_for, request
from eventqueue.bus import get_pending_tasks, update_pending_status
from roles.email_reviewer.tools import delete_email

app = Flask(__name__)

@app.route("/")
def index():
    tasks = get_pending_tasks()
    rows = ""
    for t in tasks:
        sender  = t["payload"].get("sender", "")
        subject = t["payload"].get("subject", "")
        reason  = t["reason"]
        task_id = t["id"]
        rows += f"""
        <tr>
            <td><input type="checkbox" name="task_ids" value="{task_id}" checked></td>
            <td>{sender}</td>
            <td>{subject}</td>
            <td>{reason}</td>
            <td>
                <a href="/approve/{task_id}"><button type="button" style="background:#e74c3c;color:white;border:none;padding:6px 12px;border-radius:4px;cursor:pointer">Delete</button></a>
                <a href="/reject/{task_id}"><button type="button" style="background:#95a5a6;color:white;border:none;padding:6px 12px;border-radius:4px;cursor:pointer">No</button></a>
                <a href="/later/{task_id}"><button type="button" style="background:#3498db;color:white;border:none;padding:6px 12px;border-radius:4px;cursor:pointer">Later</button></a>
            </td>
        </tr>"""

    empty = "<p style='color:#888'>No pending tasks.</p>" if not tasks else ""

    table = ""
    if tasks:
        table = f"""
        <form method="POST" action="/bulk-approve">
          <div style="display:flex;gap:10px;align-items:center;margin-bottom:12px">
            <label style="font-size:0.85rem;color:#555;cursor:pointer">
              <input type="checkbox" id="select-all" checked> Select all
            </label>
            <button type="submit" style="background:#e74c3c;color:white;border:none;padding:7px 16px;border-radius:4px;cursor:pointer;font-size:0.9rem">
              Delete selected
            </button>
            <button type="submit" form="bulk-reject-form" style="background:#95a5a6;color:white;border:none;padding:7px 16px;border-radius:4px;cursor:pointer;font-size:0.9rem">
              Reject selected
            </button>
          </div>
          <table>
            <thead><tr><th></th><th>Sender</th><th>Subject</th><th>Reason</th><th>Action</th></tr></thead>
            <tbody>{rows}</tbody>
          </table>
        </form>
        <form method="POST" action="/bulk-reject" id="bulk-reject-form">
          {"".join(f'<input type="hidden" name="task_ids" value="{t["id"]}">' for t in tasks)}
        </form>"""

    return f"""<!DOCTYPE html>
<html>
<head>
  <title>gen-claw — pending approvals</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 1000px; margin: 40px auto; padding: 0 20px; color: #222; }}
    h1 {{ font-size: 1.4rem; margin-bottom: 24px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th {{ text-align: left; padding: 10px 12px; background: #f4f4f4; font-size: 0.85rem; color: #555; }}
    td {{ padding: 10px 12px; border-bottom: 1px solid #eee; font-size: 0.9rem; vertical-align: middle; }}
    td:last-child {{ white-space: nowrap; }}
    td:last-child a {{ margin-right: 4px; }}
    tr:hover td {{ background: #fafafa; }}
  </style>
  <script>
    document.addEventListener('DOMContentLoaded', function() {{
      const selectAll = document.getElementById('select-all');
      if (!selectAll) return;
      selectAll.addEventListener('change', function() {{
        document.querySelectorAll('input[name="task_ids"]').forEach(cb => cb.checked = selectAll.checked);
      }});
    }});
  </script>
</head>
<body>
  <h1>Pending approvals ({len(tasks)})</h1>
  {empty}
  {table}
</body>
</html>"""


@app.route("/approve/<task_id>")
def approve(task_id):
    tasks = get_pending_tasks()
    task  = next((t for t in tasks if t["id"] == task_id), None)
    if task:
        email_id = task["payload"].get("email_id")
        if email_id:
            delete_email(email_id)
        update_pending_status(task_id, "approved")
    return redirect(url_for("index"))


@app.route("/bulk-approve", methods=["POST"])
def bulk_approve():
    task_ids = request.form.getlist("task_ids")
    tasks    = {t["id"]: t for t in get_pending_tasks()}
    for task_id in task_ids:
        task = tasks.get(task_id)
        if task:
            email_id = task["payload"].get("email_id")
            if email_id:
                delete_email(email_id)
            update_pending_status(task_id, "approved")
    return redirect(url_for("index"))


@app.route("/bulk-reject", methods=["POST"])
def bulk_reject():
    task_ids = request.form.getlist("task_ids")
    for task_id in task_ids:
        update_pending_status(task_id, "rejected")
    return redirect(url_for("index"))


@app.route("/reject/<task_id>")
def reject(task_id):
    update_pending_status(task_id, "rejected")
    return redirect(url_for("index"))


@app.route("/later/<task_id>")
def later(task_id):
    update_pending_status(task_id, "later")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(port=5001, debug=True)
