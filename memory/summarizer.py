import anthropic
from datetime import datetime
from pathlib import Path
from config import ANTHROPIC_API_KEY, MODEL

MEMORY_DIR = Path(__file__).parent
client     = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

ROLES = ["support_agent", "store_concierge", "email_reviewer", "personal_assistant"]

def summarize_today():
    today   = datetime.utcnow().strftime("%Y-%m-%d")
    results = []
    for role in ROLES:
        filepath = _summarize_role(role, today)
        if filepath:
            results.append(filepath)
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
    combined = "\n\n---\n\n".join(f.read_text() for f in files)
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
{sessions}"""

    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text