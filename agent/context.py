from datetime import datetime
from pathlib import Path
from agent.skills import load_skills

MEMORY_DIR = Path(__file__).parent.parent / "memory"

def build_context(role: dict, event: dict) -> str:
    role_name = role["name"]
    payload   = event["payload"]

    parts = []

    # 1 — persona
    parts.append(role["persona"])

    # 2 — role daily summary
    summary = _load_role_summary(role_name)
    if summary:
        parts.append("## What happened recently\n" + summary)

    # 3 — matched entity pages
    entities = _load_matched_entities(payload)
    if entities:
        parts.append("## Relevant entities\n" + entities)

    # 4 — skills (now dynamic, payload-matched)
    skills = load_skills(role_name, payload)
    if skills:
        parts.append("## Skills\n" + skills)

    return "\n\n---\n\n".join(parts)


def _load_role_summary(role_name: str) -> str:
    today         = datetime.utcnow().strftime("%Y-%m-%d")
    summaries_dir = MEMORY_DIR / "roles" / role_name / "summaries"

    # try today first, fall back to most recent
    today_file = summaries_dir / f"{today}.md"
    if today_file.exists():
        return today_file.read_text()

    if summaries_dir.exists():
        files = sorted(summaries_dir.glob("*.md"), reverse=True)
        if files:
            print(f"  [context] no summary for today — loading {files[0].name}")
            return files[0].read_text()

    print(f"  [context] no summary found for role: {role_name}")
    return ""


def _load_matched_entities(payload: dict) -> str:
    entities_dir = MEMORY_DIR / "shared" / "entities"
    if not entities_dir.exists():
        return ""

    matched = []

    # map payload keys to entity files
    key_to_file = {
        "customer_id": "customers.md",
        "contact_id":  "contacts.md",
        "order_id":    "known_issues.md",
    }

    loaded = set()
    for key, filename in key_to_file.items():
        if key in payload and filename not in loaded:
            filepath = entities_dir / filename
            if filepath.exists():
                matched.append(filepath.read_text())
                loaded.add(filename)
                print(f"  [context] loaded entity: {filename}")

    return "\n\n---\n\n".join(matched)
