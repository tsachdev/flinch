from pathlib import Path
import importlib

TRIGGER_TO_ROLE = {
    "support_ticket": "support_agent",
    "store_event":    "store_concierge",
    "cron":           "email_reviewer",
    "message":        "personal_assistant",
    "market_event":   "market_watcher",
}

ROLE_MAX_TOKENS = {
    "email_reviewer": 8192,
    "market_watcher": 4096,
}

def get_role(trigger_type: str) -> dict:
    role_name = TRIGGER_TO_ROLE.get(trigger_type)
    if not role_name:
        raise ValueError(f"No role registered for trigger type: {trigger_type}")
    module = importlib.import_module(f"roles.{role_name}.role")
    tools_module = importlib.import_module(f"roles.{role_name}.tools")
    skills = _load_skills(role_name)
    return {
        "name":       role_name,
        "persona":    module.PERSONA,
        "tools":      tools_module.TOOLS,
        "registry":   tools_module.TOOL_REGISTRY,
        "skills":     skills,
        "max_tokens": ROLE_MAX_TOKENS.get(role_name, 1024),
    }

def _load_skills(role_name: str) -> str:
    skills_dir = Path(__file__).parent.parent / "roles" / role_name / "skills"
    if not skills_dir.exists():
        return ""
    parts = []
    for skill_file in sorted(skills_dir.glob("*.md")):
        parts.append(skill_file.read_text())
    return "\n\n---\n\n".join(parts)

def register_trigger(trigger_type: str, role_name: str):
    TRIGGER_TO_ROLE[trigger_type] = role_name
    print(f"[registry] registered '{trigger_type}' → '{role_name}'")