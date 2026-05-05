import json
from datetime import datetime
from pathlib import Path
import google.genai as genai
from config import GOOGLE_API_KEY, MARKET_WATCHER_RECIPIENT

MEMORY_DIR = Path(__file__).parent
client     = genai.Client(api_key=GOOGLE_API_KEY)
MODEL      = "models/gemma-4-26b-a4b-it"

ROLES = ["support_agent", "email_reviewer", "personal_assistant", "market_watcher"]

def summarize_today():
    today   = datetime.utcnow().strftime("%Y-%m-%d")
    results = []
    summaries = {}
    for role in ROLES:
        filepath = _summarize_role(role, today)
        if filepath:
            results.append(filepath)
            summaries[role] = filepath.read_text()

    if summaries:
        _send_digest(summaries, today)

    return results

def _summarize_role(role: str, today: str) -> Path | None:
    sessions_dir  = MEMORY_DIR / "roles" / role / "sessions"
    summaries_dir = MEMORY_DIR / "roles" / role / "summaries"
    summaries_dir.mkdir(parents=True, exist_ok=True)

    if not sessions_dir.exists():
        return None

    files = sorted(sessions_dir.glob(f"{today}*.md"))
    if not files:
        print(f"[summarizer] {role} — no sessions today")
        return None

    print(f"[summarizer] {role} — summarising {len(files)} session(s)")
    combined = "\n\n---\n\n".join([f.read_text() for f in files])
    summary  = _call_llm(combined, today, role)

    filepath = summaries_dir / f"{today}.md"
    filepath.write_text(f"# Memory summary — {role} — {today}\n\n{summary}")
    print(f"[memory] summary written → memory/roles/{role}/summaries/{today}.md")
    return filepath

def _call_llm(sessions: str, today: str, role: str) -> str:
    prompt = f"""You are Flinch's memory summarizer for the {role} role.
Summarise the sessions below into a concise daily briefing a future {role} agent
can load as context. Be specific — include names, IDs, and outcomes.

Format exactly as:
## Patterns observed
<recurring themes, root causes, systemic issues>

## Open threads
<unresolved items, pending follow-ups>

## Entities learned
<customers, orders, contacts encountered — one line each>

## Agent performance notes
<what went well, what was uncertain, any tool failures>

---
SESSION NOTES:
{sessions[:6000]}"""

    response = client.models.generate_content(model=MODEL, contents=prompt)
    return response.text

def _send_digest(summaries: dict, today: str):
    """Send a nightly digest email summarising all agent activity."""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        import email as email_lib
        import base64
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        TOKEN_PATH = Path(__file__).parent.parent / "token.json"
        SCOPES = [
            'https://www.googleapis.com/auth/gmail.modify',
            'https://www.googleapis.com/auth/gmail.compose',
        ]

        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        service = build('gmail', 'v1', credentials=creds)

        # Build email body
        body_lines = [f"# Flinch Daily Digest — {today}\n"]
        for role, summary in summaries.items():
            body_lines.append(f"\n{'='*40}")
            body_lines.append(f"## {role.replace('_', ' ').title()}")
            body_lines.append('='*40)
            # Strip the header line from the summary
            lines = summary.splitlines()
            content = "\n".join(l for l in lines if not l.startswith("# Memory summary"))
            body_lines.append(content.strip())

        body = "\n".join(body_lines)

        message = email_lib.message.EmailMessage()
        message['To']      = MARKET_WATCHER_RECIPIENT
        message['Subject'] = f"Flinch Daily Digest — {today}"
        message.set_content(body)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service.users().messages().send(userId='me', body={'raw': raw}).execute()
        print(f"[summarizer] digest email sent → {MARKET_WATCHER_RECIPIENT}")

    except Exception as e:
        print(f"[summarizer] digest email failed (non-fatal): {e}")
